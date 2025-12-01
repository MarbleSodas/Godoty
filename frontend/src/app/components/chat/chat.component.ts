import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { SessionService, Message } from '../../services/session.service';
import { ChatService } from '../../services/chat.service';
import { ConfigService } from '../../services/config.service';

import { MessageComponent } from '../shared/message.component';
import { MessageInputComponent } from './message-input.component';
import { LoadingIndicatorComponent } from '../shared/loading-indicator.component';

// Import heroicons
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import {
  heroXCircle,
  heroChatBubbleLeftRight,
  heroAcademicCap,
  heroBolt,
  heroDocumentText,
  heroPlusCircle,
  heroArrowDown,
  heroChartBar
} from '@ng-icons/heroicons/outline';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    MessageComponent,
    MessageInputComponent,
    LoadingIndicatorComponent,
    NgIconComponent
  ],
  providers: [
    provideIcons({
      heroXCircle,
      heroChatBubbleLeftRight,
      heroAcademicCap,
      heroBolt,
      heroDocumentText,
      heroPlusCircle,
      heroArrowDown,
      heroChartBar
    })
  ],
  template: `
    <div class="chat-container">
      <!-- Chat Header -->
      <div class="chat-header">
        <div class="header-left">
          @if (currentSessionId) {
            <div class="session-info">
              <h2 class="session-title">{{ getCurrentSessionTitle() }}</h2>
              <div class="session-meta">
                <span class="mode-badge" [class]="getCurrentModeClass()">
                  {{ getCurrentModeText() }}
                </span>
                @if (currentModel) {
                  <span class="model-badge">{{ getModelDisplayName(currentModel) }}</span>
                }
              </div>
            </div>
          } @else {
            <div class="no-session">
              <h2 class="no-session-title">Select a session</h2>
              <p class="no-session-text">Choose a session from the sidebar or create a new one to start chatting</p>
            </div>
          }
        </div>

        <div class="header-right">
          @if (currentSessionId) {
            <button
              class="header-button"
              (click)="stopCurrentSession()"
              [disabled]="isProcessing"
              title="Stop current session"
            >
              <ng-icon name="heroXCircleOutline" class="w-4 h-4" />
            </button>
          }
        </div>
      </div>

      <!-- Chat Messages -->
      <div class="chat-messages" #messagesContainer>
        @if (currentSessionId && messages.length > 0) {
          <div class="messages-list">
            @for (message of messages; track message.id) {
              <app-message
                [message]="message"
                [showMetrics]="true"
              ></app-message>
            }
          </div>
        } @else if (currentSessionId) {
          <div class="empty-chat">
            <div class="empty-content">
              <ng-icon name="heroChatBubbleLeftRightOutline" class="w-12 h-12 mx-auto mb-4 text-gray-300" />
              <h3 class="empty-title">Start the conversation</h3>
              <p class="empty-text">Send a message to begin chatting with the AI assistant</p>
            </div>
          </div>
        } @else {
          <div class="welcome-screen">
            <div class="welcome-content">
              <ng-icon name="heroAcademicCapOutline" class="w-16 h-16 mx-auto mb-4 text-blue-600" />
              <h1 class="welcome-title">Welcome to Godoty</h1>
              <p class="welcome-subtitle">Your AI-powered Godot game development assistant</p>

              <div class="welcome-features">
                <div class="feature-item">
                  <div class="feature-icon">
                    <ng-icon name="heroBoltOutline" class="w-5 h-5" />
                  </div>
                  <div class="feature-text">
                    <strong>Fast Execution</strong>
                    <span>Quick task completion</span>
                  </div>
                </div>
                <div class="feature-item">
                  <div class="feature-icon">
                    <ng-icon name="heroDocumentTextOutline" class="w-5 h-5" />
                  </div>
                  <div class="feature-text">
                    <strong>Detailed Planning</strong>
                    <span>Strategic approach</span>
                  </div>
                </div>
                <div class="feature-item">
                  <div class="feature-icon">
                    <ng-icon name="heroChartBarOutline" class="w-5 h-5" />
                  </div>
                  <div class="feature-text">
                    <strong>Real-time Metrics</strong>
                    <span>Cost tracking</span>
                  </div>
                </div>
              </div>

              <div class="welcome-actions">
                <button
                  class="welcome-button primary"
                  (click)="createNewSession()"
                >
                  <ng-icon name="heroPlusCircleOutline" class="w-4 h-4" />
                  Create New Session
                </button>
              </div>
            </div>
          </div>
        }

        <!-- Processing Indicator -->
        @if (isProcessing) {
          <div class="processing-indicator">
            <app-loading-indicator
              type="dots"
              size="small"
              [message]="processingMessage"
            ></app-loading-indicator>
          </div>
        }

        <!-- Scroll to Bottom Button -->
        @if (showScrollToBottom) {
          <button
            class="scroll-to-bottom"
            (click)="scrollToBottom()"
            title="Scroll to bottom"
          >
            <ng-icon name="heroArrowDownOutline" class="w-4 h-4" />
          </button>
        }
      </div>

      <!-- Message Input -->
      @if (currentSessionId) {
        <div class="chat-input-container">
          <app-message-input
            [disabled]="isProcessing"
            [loading]="isProcessing"
            (sendMessage)="onSendMessage($event)"
            (attachmentClick)="onAttachmentClick()"
          ></app-message-input>
        </div>
      }
    </div>
  `
})
export class ChatComponent implements OnInit, OnDestroy {
  @ViewChild('messagesContainer', { static: false }) messagesContainer!: ElementRef;

  currentSessionId: string | null = null;
  messages: Message[] = [];
  isProcessing: boolean = false;
  processingMessage: string = '';
  showScrollToBottom: boolean = false;
  currentModel: string = '';
  streamingAbortController: AbortController | null = null;

  private subscriptions: Subscription[] = [];
  private autoScrollTimeout: any = null;

  constructor(
    private sessionService: SessionService,
    private chatService: ChatService,
    private configService: ConfigService
  ) {}

  ngOnInit(): void {
    this.setupSubscriptions();
  }

  ngOnDestroy(): void {
    this.cancelStreaming();
    this.subscriptions.forEach(sub => sub.unsubscribe());
    if (this.autoScrollTimeout) {
      clearTimeout(this.autoScrollTimeout);
    }
  }

  private setupSubscriptions(): void {
    // Subscribe to current session
    this.subscriptions.push(
      this.sessionService.currentSessionId.subscribe(sessionId => {
        this.currentSessionId = sessionId;
        this.messages = sessionId ? this.sessionService.getMessages(sessionId) : [];
        this.scrollToBottom();
      })
    );

    // Subscribe to messages changes
    this.subscriptions.push(
      this.sessionService.messages.subscribe(messageMap => {
        if (this.currentSessionId) {
          this.messages = messageMap.get(this.currentSessionId) || [];
          this.checkAutoScroll();
        }
      })
    );

    // Subscribe to config changes
    this.subscriptions.push(
      this.configService.config.subscribe(config => {
        this.currentModel = config.agentModel;
      })
    );
  }

  onSendMessage(event: { message: string, mode: 'planning' | 'fast', files?: File[] }): void {
    if (!this.currentSessionId || this.isProcessing) return;

    this.isProcessing = true;
    this.processingMessage = `Processing in ${event.mode} mode...`;

    // Add user message immediately
    const userMessage: Message = {
      id: `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      role: 'user',
      content: event.message,
      timestamp: new Date(),
      isStreaming: false
    };

    this.sessionService.addMessage(this.currentSessionId, userMessage);

    // Create streaming message placeholder
    const assistantMessage: Message = {
      id: `assistant-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true
    };

    this.sessionService.addMessage(this.currentSessionId, assistantMessage);

    // Start streaming
    this.startStreaming(assistantMessage.id, event.message, event.mode);
  }

  private async startStreaming(messageId: string, message: string, mode: 'planning' | 'fast'): Promise<void> {
    if (!this.currentSessionId) return;

    try {
      this.streamingAbortController = new AbortController();
      const responseGenerator = this.chatService.sendMessageStream(
        this.currentSessionId,
        message,
        mode,
        this.streamingAbortController.signal
      );

      let accumulatedContent = '';

      for await (const chunk of responseGenerator) {
        if (this.streamingAbortController?.signal.aborted) {
          break;
        }

        // Handle different chunk types
        if (chunk.type === 'text' && chunk.content) {
          accumulatedContent += chunk.content;
          this.updateStreamingMessage(messageId, { content: accumulatedContent });
        } else if (chunk.type === 'plan_created' && chunk.plan) {
          this.updateStreamingMessage(messageId, { plan: chunk.plan });
        } else if (chunk.type === 'done' || chunk.type === 'error') {
          this.finalizeStreamingMessage(messageId, chunk.type === 'error');
          break;
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
      this.finalizeStreamingMessage(messageId, true);
    } finally {
      this.isProcessing = false;
      this.processingMessage = '';
      this.streamingAbortController = null;
      this.scrollToBottom();
    }
  }

  private updateStreamingMessage(messageId: string, updates: Partial<Message>): void {
    const currentMessage = this.messages.find(msg => msg.id === messageId);
    if (currentMessage) {
      const updatedMessage = { ...currentMessage, ...updates };
      this.sessionService.updateMessage(this.currentSessionId!, messageId, updatedMessage);
      this.checkAutoScroll();
    }
  }

  private finalizeStreamingMessage(messageId: string, isError: boolean = false): void {
    this.updateStreamingMessage(messageId, {
      isStreaming: false,
      content: isError ? 'An error occurred during message processing.' : this.messages.find(msg => msg.id === messageId)?.content || ''
    });
  }

  private cancelStreaming(): void {
    if (this.streamingAbortController) {
      this.streamingAbortController.abort();
      this.streamingAbortController = null;
    }
  }

  createNewSession(): void {
    this.sessionService.createSession();
  }

  stopCurrentSession(): void {
    if (this.currentSessionId && !this.isProcessing) {
      this.chatService.stopSession(this.currentSessionId).subscribe({
        next: () => {
          this.cancelStreaming();
          this.isProcessing = false;
          this.processingMessage = '';
        },
        error: (error) => {
          console.error('Failed to stop session:', error);
        }
      });
    }
  }

  onAttachmentClick(): void {
    // TODO: Implement file attachment handling
    console.log('File attachment clicked');
  }

  scrollToBottom(): void {
    setTimeout(() => {
      if (this.messagesContainer?.nativeElement) {
        this.messagesContainer.nativeElement.scrollTop = this.messagesContainer.nativeElement.scrollHeight;
      }
    }, 100);
  }

  private checkAutoScroll(): void {
    if (this.autoScrollTimeout) {
      clearTimeout(this.autoScrollTimeout);
    }

    this.autoScrollTimeout = setTimeout(() => {
      if (this.messagesContainer?.nativeElement) {
        const { scrollTop, scrollHeight, clientHeight } = this.messagesContainer.nativeElement;
        const isNearBottom = scrollHeight - (scrollTop + clientHeight) < 100;
        this.showScrollToBottom = !isNearBottom;

        if (isNearBottom) {
          this.scrollToBottom();
        }
      }
    }, 100);
  }

  getCurrentSessionTitle(): string {
    if (!this.currentSessionId) return '';
    const session = this.sessionService.activeSessions.value.find(s => s.id === this.currentSessionId);
    return session?.title || 'Untitled Session';
  }

  getCurrentModeClass(): string {
    const mode = this.configService.getMode();
    return mode === 'planning' ? 'planning' : 'fast';
  }

  getCurrentModeText(): string {
    const mode = this.configService.getMode();
    return mode.charAt(0).toUpperCase() + mode.slice(1);
  }

  getModelDisplayName(modelId: string): string {
    const parts = modelId.split('/');
    return parts[parts.length - 1] || modelId;
  }
}