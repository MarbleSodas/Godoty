import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, ElementRef, ViewChild, AfterViewChecked, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatSession, ChatMessage, MessageStatus } from '../../models/command.model';
import { ChatMessageComponent } from '../chat-message/chat-message.component';

@Component({
  selector: 'app-chat-view',
  standalone: true,
  imports: [CommonModule, FormsModule, ChatMessageComponent],
  templateUrl: './chat-view.component.html',
  styleUrls: ['./chat-view.component.css']
})
export class ChatViewComponent implements OnChanges, AfterViewChecked, OnDestroy {
  @Input() session: ChatSession | null = null;
  @Input() isProcessing: boolean = false;
  @Input() processingStatus: MessageStatus | null = null;
  @Input() disabled: boolean = false;
  @Output() submitCommand = new EventEmitter<string>();
  @ViewChild('messagesContainer') private messagesContainer?: ElementRef;

  input: string = '';
  private shouldScrollToBottom = false;
  private autoScrollEnabled = true;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['session'] && this.session) {
      this.shouldScrollToBottom = true;
    }
  }

  ngAfterViewChecked(): void {
    if (this.shouldScrollToBottom && this.autoScrollEnabled) {
      this.scrollToBottom();
      this.shouldScrollToBottom = false;
    }
  }

  ngOnDestroy(): void {
    // Cleanup if needed
  }

  private scrollToBottom(): void {
    if (this.messagesContainer) {
      try {
        this.messagesContainer.nativeElement.scrollTop =
          this.messagesContainer.nativeElement.scrollHeight;
      } catch (err) {
        console.error('Error scrolling to bottom:', err);
      }
    }
  }

  onScroll(): void {
    if (this.messagesContainer) {
      const element = this.messagesContainer.nativeElement;
      const isAtBottom = element.scrollHeight - element.scrollTop <= element.clientHeight + 50;
      this.autoScrollEnabled = isAtBottom;
    }
  }

  getProcessingStatusText(): string {
    if (!this.processingStatus) return 'Processing...';

    switch (this.processingStatus) {
      case 'thinking':
        return '🤔 Thinking...';
      case 'gathering':
        return '📚 Gathering data...';
      case 'generating':
        return '⚡ Generating response...';
      case 'streaming':
        return '📝 Streaming response...';
      case 'executing':
        return '⚙️ Executing action...';
      case 'sending':
        return '📤 Sending...';
      default:
        return '⏳ Processing...';
    }
  }

  getSuccessRate(): number {
    if (!this.session || this.session.metadata.total_commands === 0) {
      return 0;
    }
    return (this.session.metadata.successful_commands / this.session.metadata.total_commands) * 100;
  }

  formatDate(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleDateString();
  }

  formatTime(timestamp: number): string {
    return new Date(timestamp * 1000).toLocaleTimeString();
  }

  trackByMessageId(index: number, msg: ChatMessage): string {
    return msg.id;
  }

  handleSubmit(event: Event): void {
    event.preventDefault();
    if (this.input.trim() && !this.disabled) {
      this.submitCommand.emit(this.input.trim());
      this.input = '';
    }
  }
}

