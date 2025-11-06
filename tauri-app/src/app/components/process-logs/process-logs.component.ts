import { Component, Input, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ProcessLogService } from '../../services/process-log.service';
import { ProcessLogEntry, LogLevel } from '../../models/process-log.model';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-process-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './process-logs.component.html',
  styleUrls: ['./process-logs.component.css']
})
export class ProcessLogsComponent implements OnDestroy {
  @Input() sessionId?: string | null;

  entries: ProcessLogEntry[] = [];
  filtered: ProcessLogEntry[] = [];
  expandedId: string | null = null;

  // Filters
  showInfo = true;
  showWarning = true;
  showError = true;

  showDebug = true;
  private sub?: Subscription;

  constructor(private logs: ProcessLogService) {
    this.sub = this.logs.getLogs().subscribe(list => {
      this.entries = list;
      this.applyFilters();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  toggleExpand(id: string): void {
    this.expandedId = this.expandedId === id ? null : id;
  }

  levelIcon(level: LogLevel): string {
    switch (level) {
      case 'debug': return '🐞';
      case 'info': return 'ℹ️';
      case 'warning': return '⚠️';
      case 'error': return '❌';
    }
  }

  statusBadge(entry: ProcessLogEntry): string {
    switch (entry.status) {
      case 'processing': return 'processing';
      case 'waiting': return 'waiting';
      case 'completed': return 'completed';
      case 'error': return 'error';
      default: return 'idle';
    }
  }

  formatTime(ms: number): string {
    const d = new Date(ms);
    return d.toLocaleTimeString();
  }

  applyFilters(): void {
    const allowedLevels = new Set<LogLevel>([
      ...(this.showDebug ? ['debug'] as LogLevel[] : []),
      ...(this.showInfo ? ['info'] as LogLevel[] : []),
      ...(this.showWarning ? ['warning'] as LogLevel[] : []),
      ...(this.showError ? ['error'] as LogLevel[] : []),
    ]);

    this.filtered = this.entries.filter(e => {
      if (this.sessionId && e.sessionId && e.sessionId !== this.sessionId) return false;
      return allowedLevels.has(e.level);
    });
  }
}

