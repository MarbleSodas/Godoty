import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatMessage, MessageStatus } from '../../models/command.model';

@Component({
  selector: 'app-chat-message',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './chat-message.component.html',
  styleUrls: ['./chat-message.component.css']
})
export class ChatMessageComponent {
  @Input() message!: ChatMessage;
  @Input() showThoughts: boolean = true;

  thoughtsExpanded: boolean = true; // Default to expanded to show agent thoughts
  contextExpanded: boolean = false;

  formatTimestamp(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleTimeString();
  }

  toggleThoughts(): void {
    this.thoughtsExpanded = !this.thoughtsExpanded;
  }

  toggleContext(): void {
    this.contextExpanded = !this.contextExpanded;
  }

  getRoleIcon(): string {
    switch (this.message.role) {
      case 'user':
        return '👤';
      case 'assistant':
        return '🤖';
      case 'system':
        return '🤔'; // Agent thought icon
      default:
        return '💬';
    }
  }

  getStatusIcon(): string {
    if (!this.message.status) return '';

    switch (this.message.status) {
      case 'sending':
        return '📤';
      case 'sent':
        return '✓';
      case 'thinking':
        return '🤔';
      case 'gathering':
        return '📚';
      case 'generating':
        return '⚡';
      case 'streaming':
        return '📝';
      case 'searching_web':
        return '🔎';
      case 'executing':
        return '⚙️';
      case 'complete':
        return '✓✓';
      case 'error':
        return '❌';
      default:
        return '';
    }
  }

  getStatusLabel(): string {
    if (!this.message.status) return '';

    switch (this.message.status) {
      case 'sending':
        return 'Sending';
      case 'sent':
        return 'Sent';
      case 'thinking':
        return 'Thinking';
      case 'gathering':
        return 'Gathering Data';
      case 'searching_web':
        return 'Searching the web';
      case 'generating':
        return 'Generating';
      case 'streaming':
        return 'Streaming';
      case 'executing':
        return 'Executing';
      case 'complete':
        return 'Complete';
      case 'error':
        return 'Error';
      default:
        return '';
    }
  }

  getStatusClass(): string {
    if (!this.message.status) return '';

    switch (this.message.status) {
      case 'sending':
      case 'sent':
        return 'status-sent';
      case 'thinking':
      case 'gathering':
      case 'generating':
      case 'streaming':
      case 'searching_web':
      case 'executing':
        return 'status-processing';
      case 'complete':
        return 'status-complete';
      case 'error':
        return 'status-error';
      default:
        return '';
    }
  }

  isProcessing(): boolean {
    return this.message.status === 'thinking' ||
           this.message.status === 'gathering' ||
           this.message.status === 'generating' ||
           this.message.status === 'streaming' ||
           this.message.status === 'searching_web' ||
           this.message.status === 'executing';
  }

  getRoleLabel(): string {
    switch (this.message.role) {
      case 'user':
        return 'You';
      case 'assistant':
        return 'Godoty AI';
      case 'system':
        return 'Agent Thought'; // Label for agent thinking messages
      default:
        return 'Unknown';
    }
  }
}

