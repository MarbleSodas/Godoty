import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { invoke } from '@tauri-apps/api/core';
import { KnowledgeBaseStatus, KnowledgeDocument } from '../../models/knowledge-base.model';

@Component({
  selector: 'app-knowledge-base-status',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './knowledge-base-status.component.html',
  styleUrls: ['./knowledge-base-status.component.css']
})
export class KnowledgeBaseStatusComponent implements OnInit, OnDestroy {
  status: KnowledgeBaseStatus | null = null;
  documents: KnowledgeDocument[] = [];
  isRebuilding: boolean = false;
  showDocuments: boolean = false;
  private refreshInterval: any;

  // Expose Object to template
  Object = Object;

  async ngOnInit(): Promise<void> {
    await this.loadStatus();
    // Refresh status every 5 seconds
    this.refreshInterval = setInterval(() => this.loadStatus(), 5000);
  }

  ngOnDestroy(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }

  async loadStatus(): Promise<void> {
    try {
      this.status = await invoke<KnowledgeBaseStatus>('get_knowledge_base_status');
    } catch (error) {
      console.error('Failed to load knowledge base status:', error);
    }
  }

  async loadDocuments(): Promise<void> {
    try {
      this.documents = await invoke<KnowledgeDocument[]>('get_docs_kb_documents');
      this.showDocuments = true;
    } catch (error) {
      console.error('Failed to load documents:', error);
    }
  }

  async handleRebuild(): Promise<void> {
    this.isRebuilding = true;
    try {
      const result = await invoke<string>('rebuild_docs_kb');
      console.log(result);
      await this.loadStatus();
      if (this.showDocuments) {
        await this.loadDocuments();
      }
    } catch (error) {
      console.error('Failed to rebuild docs KB:', error);
    } finally {
      this.isRebuilding = false;
    }
  }

  toggleDocuments(): void {
    if (this.showDocuments) {
      this.showDocuments = false;
      this.documents = [];
    } else {
      this.loadDocuments();
    }
  }

  getStatusIcon(): string {
    if (!this.status) return '⚪';
    return this.status.initialized ? '✅' : '⚪';
  }

  getStatusText(): string {
    if (!this.status) return 'Unknown';
    if (!this.status.initialized) return 'Not Initialized';
    return `${this.status.docs_kb_count} documents`;
  }

  getStatusColor(): string {
    if (!this.status) return 'text-white/50';
    return this.status.initialized ? 'text-green-400' : 'text-white/50';
  }

  formatTimestamp(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleString();
  }

  truncateContent(content: string, maxLength: number = 200): string {
    if (content.length <= maxLength) return content;
    return content.substring(0, maxLength) + '...';
  }
}

