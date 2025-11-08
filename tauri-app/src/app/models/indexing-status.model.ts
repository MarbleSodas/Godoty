// Indexing Status Types
export type IndexingStatusType = 'NotStarted' | 'Indexing' | 'Complete' | 'Failed';

export interface IndexingStatus {
  type: IndexingStatusType;
  message?: string; // Error message for Failed status
}

export interface IndexingStatusResponse {
  projectPath: string | null;
  status: IndexingStatus;
}

export interface IndexingStatusEvent {
  projectPath: string | null;
  status: IndexingStatus;
}

