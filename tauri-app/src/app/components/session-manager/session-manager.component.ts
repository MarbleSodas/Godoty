import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatSession } from '../../models/command.model';

@Component({
  selector: 'app-session-manager',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './session-manager.component.html',
  styleUrls: ['./session-manager.component.css']
})
export class SessionManagerComponent {
  @Input() sessions: ChatSession[] = [];
  @Input() activeSessionId: string | null = null;
  @Output() createSession = new EventEmitter<string>();
  @Output() selectSession = new EventEmitter<string>();
  @Output() deleteSession = new EventEmitter<string>();
  @Output() clearAllSessions = new EventEmitter<void>();

  handleCreateSession(): void {
    // Instantly create a new session with a placeholder title
    this.createSession.emit('New Chat');
  }

  handleSelectSession(sessionId: string): void {
    this.selectSession.emit(sessionId);
  }

  handleDeleteSession(sessionId: string, event: Event): void {
    event.stopPropagation();
    if (confirm('Are you sure you want to delete this session?')) {
      this.deleteSession.emit(sessionId);
    }
  }

  handleClearAll(): void {
    if (confirm('Are you sure you want to delete all sessions? This cannot be undone.')) {
      this.clearAllSessions.emit();
    }
  }

  formatDate(timestamp: number): string {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString();
  }

  getSessionPreview(session: ChatSession): string {
    const msgs = (session.messages || []).filter(m => !m.sessionId || m.sessionId === session.id);
    if (msgs.length === 0) {
      return 'No messages yet';
    }
    const lastMessage = msgs[msgs.length - 1];
    return lastMessage.content.substring(0, 60) + (lastMessage.content.length > 60 ? '...' : '');
  }

  getFilteredCount(session: ChatSession): number {
    return (session.messages || []).filter(m => !m.sessionId || m.sessionId === session.id).length;
  }

  trackBySessionId(_index: number, s: ChatSession): string {
    return s.id;
  }

}

