// Knowledge Base Types
export interface KnowledgeBaseStatus {
  initialized: boolean;
  plugin_kb_count: number;
  docs_kb_count: number;
}

export interface KnowledgeDocument {
  id: string;
  content: string;
  metadata: Record<string, string>;
  embedding: number[] | null;
  created_at: number;
  updated_at: number;
}

