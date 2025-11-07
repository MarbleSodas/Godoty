import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatSession } from '../../models/command.model';

@Component({
  selector: 'app-chat-selector',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './chat-selector.component.html',
  styleUrls: ['./chat-selector.component.css']
})
export class ChatSelectorComponent {
  @Input() sessions: ChatSession[] = [];
  @Input() activeSession: ChatSession | null = null;
  @Output() selectSession = new EventEmitter<string>();
  @Output() createSession = new EventEmitter<void>();

  isExpanded: boolean = false;

  toggleDropdown(): void {
    this.isExpanded = !this.isExpanded;
  }

  handleSelectSession(sessionId: string): void {
    this.selectSession.emit(sessionId);
    this.isExpanded = false;
  }

  handleCreateSession(): void {
    this.createSession.emit();
    this.isExpanded = false;
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
    const preview = lastMessage.content.substring(0, 50);
    return preview.length < lastMessage.content.length ? `${preview}...` : preview;
  }
}

