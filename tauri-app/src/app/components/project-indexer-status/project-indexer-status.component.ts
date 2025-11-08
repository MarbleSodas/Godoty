import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IndexingStatus } from '../../models/indexing-status.model';

@Component({
  selector: 'app-project-indexer-status',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './project-indexer-status.component.html',
  styleUrls: ['./project-indexer-status.component.css']
})
export class ProjectIndexerStatusComponent {
  @Input() projectPath: string | null = null;
  @Input() status: IndexingStatus | null = null;

  getStatusIcon(): string {
    if (!this.status) return '⚪';
    
    switch (this.status.type) {
      case 'NotStarted':
        return '⚪';
      case 'Indexing':
        return '🔄';
      case 'Complete':
        return '✅';
      case 'Failed':
        return '❌';
      default:
        return '⚪';
    }
  }

  getStatusText(): string {
    if (!this.status) return 'Unknown';
    
    switch (this.status.type) {
      case 'NotStarted':
        return 'Not Started';
      case 'Indexing':
        return 'Indexing...';
      case 'Complete':
        return 'Complete';
      case 'Failed':
        return `Failed: ${this.status.message || 'Unknown error'}`;
      default:
        return 'Unknown';
    }
  }

  getStatusColor(): string {
    if (!this.status) return 'text-white/50';
    
    switch (this.status.type) {
      case 'NotStarted':
        return 'text-white/50';
      case 'Indexing':
        return 'text-blue-400';
      case 'Complete':
        return 'text-green-400';
      case 'Failed':
        return 'text-red-400';
      default:
        return 'text-white/50';
    }
  }
}

