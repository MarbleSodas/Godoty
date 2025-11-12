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
      case 'analyzing_visual':
        return '🖼️ Analyzing visual snapshot...';
      case 'researching_tutorials':
        return '🔎 Researching tutorials...';
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

  filteredMessages(session: ChatSession | null): ChatMessage[] {
    if (!session || !session.messages) return [];
    const sid = session.id;

    // Filter messages for this session
    const filtered = session.messages.filter(m =>
      (!m.sessionId || m.sessionId === sid)
    );

    // Remove duplicates by ID (in case frontend and backend both created messages)
    const uniqueMessages = filtered.reduce((acc, msg) => {
      if (!acc.find(m => m.id === msg.id)) {
        acc.push(msg);
      }
      return acc;
    }, [] as ChatMessage[]);

    // Remove optimistic user messages if a real user message exists with same content and similar timestamp
    // Optimistic messages have IDs starting with 'tmp-'
    const withoutOptimistic = uniqueMessages.filter(msg => {
      if (!msg.id.startsWith('tmp-')) return true; // Keep non-optimistic messages

      // Check if there's a real user message with same content within 5 seconds
      const hasDuplicate = uniqueMessages.some(other =>
        other.id !== msg.id &&
        !other.id.startsWith('tmp-') &&
        other.role === 'user' &&
        other.content === msg.content &&
        Math.abs(other.timestamp - msg.timestamp) <= 5
      );

      return !hasDuplicate; // Remove optimistic message if duplicate exists
    });

    // Sort by timestamp first, then by role to ensure correct order within the same second:
    // 1. User message (input) - role priority 0
    // 2. System messages (agent thoughts/streaming) - role priority 1
    // 3. Assistant message (results with metrics) - role priority 2
    return withoutOptimistic.sort((a, b) => {
      // Primary sort: timestamp
      const timeDiff = a.timestamp - b.timestamp;
      if (timeDiff !== 0) return timeDiff;

      // Secondary sort: role priority (user < system < assistant)
      const rolePriority = (role: string): number => {
        if (role === 'user') return 0;
        if (role === 'system') return 1;
        if (role === 'assistant') return 2;
        return 3;
      };

      return rolePriority(a.role) - rolePriority(b.role);
    });
  }

  trackByMessageId(index: number, msg: ChatMessage): string {
    return msg.id;
  }

  getUserMessageCount(session: ChatSession | null): number {
    if (!session || !session.messages) return 0;
    return this.filteredMessages(session).filter(m => m.role === 'user').length;
  }

  handleSubmit(event: Event): void {
    event.preventDefault();
    if (this.input.trim() && !this.disabled) {
      this.submitCommand.emit(this.input.trim());
      this.input = '';
    }
  }
}

