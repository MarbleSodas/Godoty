use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResultItem {
    pub title: String,
    pub url: String,
    pub snippet: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResults {
    pub provider: String,
    pub query: String,
    pub took_ms: u128,
    pub results: Vec<SearchResultItem>,
}

/// Minimal client for Tavily Search API (https://docs.tavily.com/)
/// Expects environment variable TAVILY_API_KEY unless provided explicitly.
pub struct TavilyClient {
    api_key: String,
}

impl TavilyClient {
    pub fn new(api_key: String) -> Self {
        Self { api_key }
    }

    pub async fn search(&self, query: &str, max_results: usize) -> anyhow::Result<SearchResults> {
        let client = reqwest::Client::new();
        let body = json!({
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results.min(10),
        });
        let start = std::time::Instant::now();
        let resp = client
            .post("https://api.tavily.com/search")
            .json(&body)
            .send()
            .await?;

        let took_ms = start.elapsed().as_millis();
        if !resp.status().is_success() {
            let text = resp.text().await.unwrap_or_default();
            anyhow::bail!("tavily search failed: {}", text);
        }
        let v: serde_json::Value = resp.json().await?;
        let mut items: Vec<SearchResultItem> = Vec::new();
        if let Some(arr) = v.get("results").and_then(|x| x.as_array()) {
            for it in arr.iter().take(max_results) {
                items.push(SearchResultItem {
                    title: it
                        .get("title")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string(),
                    url: it
                        .get("url")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string(),
                    snippet: it
                        .get("content")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string(),
                });
            }
        }
        Ok(SearchResults {
            provider: "tavily".into(),
            query: query.into(),
            took_ms,
            results: items,
        })
    }
}

/// Convenience enum for multiple providers; expand later if needed
#[allow(dead_code)]
pub enum SearchProviderClient {
    Tavily(TavilyClient),
}

#[allow(dead_code)]
impl SearchProviderClient {
    pub async fn search(&self, query: &str, max_results: usize) -> anyhow::Result<SearchResults> {
        match self {
            SearchProviderClient::Tavily(c) => c.search(query, max_results).await,
        }
    }
}
