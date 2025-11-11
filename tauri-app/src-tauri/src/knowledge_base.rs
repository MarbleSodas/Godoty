use anyhow::Result;
use fastembed::{TextEmbedding, InitOptions, EmbeddingModel};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::sync::Arc;
use tokio::sync::Mutex;

/// Represents a document in the knowledge base
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeDocument {
    pub id: String,
    pub content: String,
    pub metadata: HashMap<String, String>,
    pub embedding: Option<Vec<f32>>,
    pub created_at: u64,
    pub updated_at: u64,
}

/// Knowledge base for storing and retrieving documents with semantic search
#[derive(Clone)]
pub struct KnowledgeBase {
    name: String,
    documents: Arc<tokio::sync::RwLock<Vec<KnowledgeDocument>>>,
    embedding_model: Arc<Mutex<TextEmbedding>>,
}

impl KnowledgeBase {
    /// Create a new knowledge base
    pub fn new(name: &str) -> Result<Self> {
        // Initialize the embedding model (using all-MiniLM-L6-v2 to match Python RAG server)
        let model = TextEmbedding::try_new(
            InitOptions::new(EmbeddingModel::AllMiniLML6V2)
        )?;

        Ok(Self {
            name: name.to_string(),
            documents: Arc::new(tokio::sync::RwLock::new(Vec::new())),
            embedding_model: Arc::new(Mutex::new(model)),
        })
    }

    /// Add a document to the knowledge base
    pub async fn add_document(
        &self,
        id: String,
        content: String,
        metadata: HashMap<String, String>,
    ) -> Result<()> {
        let embedding = self.generate_embedding(&content).await?;

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_secs();

        let document = KnowledgeDocument {
            id: id.clone(),
            content,
            metadata,
            embedding: Some(embedding),
            created_at: now,
            updated_at: now,
        };

        let mut docs = self.documents.write().await;

        // Remove existing document with same ID if it exists
        docs.retain(|d| d.id != id);

        docs.push(document);

        Ok(())
    }

    /// Search for documents using semantic similarity
    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<KnowledgeDocument>> {
        let query_embedding = self.generate_embedding(query).await?;

        let docs = self.documents.read().await;

        let mut scored_docs: Vec<(f32, KnowledgeDocument)> = docs
            .iter()
            .filter_map(|doc| {
                if let Some(embedding) = &doc.embedding {
                    let similarity = cosine_similarity(&query_embedding, embedding);
                    Some((similarity, doc.clone()))
                } else {
                    None
                }
            })
            .collect();

        // Sort by similarity (descending)
        scored_docs.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

        // Take top K results
        Ok(scored_docs
            .into_iter()
            .take(top_k)
            .map(|(_, doc)| doc)
            .collect())
    }

    /// Generate embedding for text using local fastembed model
    async fn generate_embedding(&self, text: &str) -> Result<Vec<f32>> {
        let text_owned = text.to_string();
        let model = self.embedding_model.clone();

        // Run embedding in a blocking task since fastembed is synchronous
        let embedding = tokio::task::spawn_blocking(move || {
            let mut model = model.blocking_lock();
            let embeddings = model.embed(vec![text_owned], None)?;
            embeddings.into_iter().next()
                .ok_or_else(|| anyhow::anyhow!("No embedding returned"))
        }).await??;

        Ok(embedding)
    }

    /// Save knowledge base to disk
    pub async fn save_to_disk(&self, storage_dir: &Path) -> Result<()> {
        let mut path = storage_dir.to_path_buf();
        path.push(format!("{}_kb.json", self.name));

        let docs = self.documents.read().await;
        let json = serde_json::to_string_pretty(&*docs)?;
        fs::write(path, json)?;

        Ok(())
    }

    /// Load knowledge base from disk
    pub async fn load_from_disk(&self, storage_dir: &Path) -> Result<()> {
        let mut path = storage_dir.to_path_buf();
        path.push(format!("{}_kb.json", self.name));

        if !path.exists() {
            return Ok(()); // No saved data yet
        }

        let content = fs::read_to_string(path)?;
        let loaded_docs: Vec<KnowledgeDocument> = serde_json::from_str(&content)?;

        let mut docs = self.documents.write().await;
        *docs = loaded_docs;

        Ok(())
    }


    /// Get document count
    pub async fn count(&self) -> usize {
        let docs = self.documents.read().await;
        docs.len()
    }

    /// Get all documents (for viewing)
    pub async fn get_all_documents(&self) -> Vec<KnowledgeDocument> {
        let docs = self.documents.read().await;
        docs.clone()
    }

    /// Clear all documents
    pub async fn clear(&self) -> Result<()> {
        let mut docs = self.documents.write().await;
        docs.clear();
        Ok(())
    }
}

/// Calculate cosine similarity between two vectors
fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() {
        return 0.0;
    }

    let dot_product: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let magnitude_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let magnitude_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();

    if magnitude_a == 0.0 || magnitude_b == 0.0 {
        return 0.0;
    }

    dot_product / (magnitude_a * magnitude_b)
}
