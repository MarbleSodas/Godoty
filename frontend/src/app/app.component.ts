import { Component, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy, model, OnInit, inject, EffectRef, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Session, Message as ServiceMessage, ToolCall as ServiceToolCall } from './services/chat.service';
import { DesktopService, GodotStatus } from './services/desktop.service';
import { catchError, of, switchMap, tap } from 'rxjs';

// --- Interfaces ---

interface ToolCall {
  toolName: string;
  input: string;
  output?: string;
  status: 'pending' | 'success' | 'error';
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  reasoning?: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
  error?: string;
  metrics?: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    model_id: string;
  };
}

interface Metrics {
  latency: number;
  tokensPerSec: number;
}

// --- Main App Component ---

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex h-screen w-full bg-[#202531] text-gray-200 font-sans overflow-hidden selection:bg-[#478cbf] selection:text-white">
      
      <!-- Sidebar -->
      <aside 
        class="flex-shrink-0 bg-[#1a1e29] border-r border-[#2d3546] transition-all duration-300 ease-in-out flex flex-col"
        [class.w-64]="sidebarOpen()"
        [class.w-0]="!sidebarOpen()"
        [class.overflow-hidden]="!sidebarOpen()"
      >
        <div class="p-4 flex items-center justify-between border-b border-[#2d3546]">
          <div class="flex items-center space-x-2 font-bold text-[#478cbf]">
            <!-- Godot-like Icon -->
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/> 
              <circle cx="9" cy="13" r="1.5" />
              <circle cx="15" cy="13" r="1.5" />
            </svg>
            <span>GODOTY</span>
          </div>
          <button (click)="createNewSession()" class="p-1.5 hover:bg-[#2d3546] rounded-md transition-colors text-gray-400 hover:text-white" title="New Chat">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
            </svg>
          </button>
        </div>

        <div class="flex-1 overflow-y-auto py-2">
          <div class="px-4 pb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">History</div>
          @for (session of sessions(); track session.id) {
            <div
              (click)="selectSession(session.id)"
              (keydown.enter)="selectSession(session.id)"
              (keydown.space)="selectSession(session.id); $event.preventDefault()"
              role="button"
              tabindex="0"
              [attr.aria-label]="'Select session: ' + session.title"
              class="relative w-full text-left px-4 py-3 text-sm hover:bg-[#2d3546] transition-colors border-l-2 flex justify-between items-center group cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#478cbf]/50"
              [class.border-[#478cbf]]="activeSessionId() === session.id"
              [class.bg-[#262c3b]]="activeSessionId() === session.id"
              [class.text-white]="activeSessionId() === session.id"
              [class.text-gray-400]="activeSessionId() !== session.id"
              [class.border-transparent]="activeSessionId() !== session.id"
            >
              <span class="flex-1 truncate">
                {{ session.title }}
              </span>
              <button
                (click)="deleteSession(session.id, $event)"
                class="opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-500/10 rounded"
                title="Delete session"
                aria-label="Delete session"
              >
                🗑️
              </button>
            </div>
          }
        </div>
        
        <div class="p-4 border-t border-[#2d3546] flex items-center space-x-3">
          <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-[#478cbf] to-cyan-400 flex items-center justify-center text-xs font-bold text-white">
            GD
          </div>
          <div class="text-sm">
            <div class="font-medium text-gray-200">GameDev User</div>
            <div class="text-xs text-gray-500">Pro Plan</div>
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="flex-1 flex flex-col relative min-w-0">
        
        <!-- Header -->
        <header class="h-14 border-b border-[#2d3546] bg-[#202531]/95 backdrop-blur flex items-center justify-between px-4 z-10 sticky top-0">
          <div class="flex items-center">
            <button (click)="toggleSidebar()" class="mr-3 p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
            <div class="flex flex-col">
              <span class="font-semibold text-gray-200 text-sm">
                {{ godotStatus()?.project_settings?.name || 'Godoty 4.3 Assistant' }}
              </span>
              <span class="text-[10px] flex items-center gap-1" [class.text-[#478cbf]]="isGodotConnected()" [class.text-red-500]="!isGodotConnected()">
                <span class="w-1.5 h-1.5 rounded-full animate-pulse" [class.bg-green-500]="isGodotConnected()" [class.bg-red-500]="!isGodotConnected()"></span>
                {{ isGodotConnected() ? 'Online' : 'Offline' }} 
                @if(godotStatus()?.godot_version) {
                   - {{ godotStatus()?.godot_version }}
                }
              </span>
            </div>
          </div>

          <!-- Metrics Panel -->
          <div class="flex items-center gap-4 text-xs font-mono text-gray-500 bg-[#1a1e29] px-3 py-1.5 rounded border border-[#2d3546]">
            <div class="flex items-center gap-1.5" title="Inference Latency">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clip-rule="evenodd" />
              </svg>
              <span>{{ metrics().latency | number:'1.0-0' }}ms</span>
            </div>
            <div class="w-px h-3 bg-[#2d3546]"></div>
            <div class="flex items-center gap-1.5" title="Tokens per second">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                <path fill-rule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clip-rule="evenodd" />
              </svg>
              <span>{{ metrics().tokensPerSec | number:'1.1-1' }} t/s</span>
            </div>
          </div>
        </header>

        <!-- Chat Area -->
        <div class="flex-1 overflow-y-auto p-4 scroll-smooth" #scrollContainer>
          <div class="max-w-3xl mx-auto space-y-6 pb-20">
            
            <!-- Empty State -->
            @if (messages().length === 0) {
              <div class="flex flex-col items-center justify-center h-full py-20 opacity-50 select-none">
                <div class="w-16 h-16 bg-[#2d3546] rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-[#478cbf]/10">
                   <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-8 h-8 text-[#478cbf]">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/> 
                  </svg>
                </div>
                <h2 class="text-xl font-medium text-gray-300">How can I help with your Godot project?</h2>
                <p class="text-sm text-gray-500 mt-2">Ask about GDScript, shaders, or scene composition.</p>
              </div>
            }

            @for (msg of messages(); track msg.id) {
              <!-- User Message -->
              @if (msg.role === 'user') {
                <div class="flex justify-end animate-fade-in-up">
                  <div class="bg-[#2d3546] text-gray-100 px-4 py-3 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm border border-[#3b4458]">
                    <div class="text-sm whitespace-pre-wrap leading-relaxed">{{ msg.content }}</div>
                  </div>
                </div>
              }

              <!-- Assistant Message -->
              @if (msg.role === 'assistant') {
                <div class="flex gap-4 animate-fade-in pr-4">
                  <div class="flex-shrink-0 mt-1">
                    <div class="w-8 h-8 rounded-lg bg-[#478cbf] flex items-center justify-center shadow-lg shadow-blue-500/20">
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="white" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                      </svg>
                    </div>
                  </div>
                  
                  <div class="flex-1 space-y-4 min-w-0">
                    
                    <!-- Reasoning Block -->
                    @if (msg.reasoning) {
                      <div class="group">
                        <details [open]="msg.isStreaming" class="bg-[#1a1e29]/50 border-l-2 border-[#478cbf]/30 rounded-r pl-3 py-1 open:bg-[#1a1e29] open:py-2 transition-all">
                          <summary class="text-xs font-mono text-[#478cbf] cursor-pointer hover:text-blue-300 select-none flex items-center gap-2 outline-none">
                            <span class="opacity-70 group-hover:opacity-100 transition-opacity">thought process</span>
                            @if (msg.isStreaming && !msg.content) {
                                <span class="animate-pulse w-1.5 h-1.5 bg-[#478cbf] rounded-full"></span>
                            }
                          </summary>
                          <div class="mt-2 text-xs text-gray-400 font-mono leading-relaxed whitespace-pre-wrap animate-fade-in pl-1">
                            {{ msg.reasoning }}
                          </div>
                        </details>
                      </div>
                    }

                    <!-- Tool Calls -->
                    @if (msg.toolCalls && msg.toolCalls.length > 0) {
                        @for (tool of msg.toolCalls; track tool) {
                            <div class="my-2 border border-[#3b4458] rounded-md bg-[#161922] overflow-hidden font-mono text-xs shadow-sm">
                                <div class="bg-[#1f2430] px-3 py-2 flex items-center justify-between border-b border-[#2d3546]">
                                    <div class="flex items-center gap-2 text-gray-300">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-[#478cbf]">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 18" />
                                        </svg>
                                        <span>Called: <span class="text-[#478cbf]">{{ tool.toolName }}</span></span>
                                    </div>
                                    <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold"
                                        [class.bg-yellow-900]="tool.status === 'pending'"
                                        [class.text-yellow-200]="tool.status === 'pending'"
                                        [class.bg-green-900]="tool.status === 'success'"
                                        [class.text-green-200]="tool.status === 'success'"
                                        [class.bg-red-900]="tool.status === 'error'"
                                        [class.text-red-200]="tool.status === 'error'">
                                        {{ tool.status }}
                                    </span>
                                </div>
                                <div class="p-3 text-gray-400">
                                    <div class="mb-1 text-gray-500 select-none">// Input</div>
                                    <div class="mb-2 text-[#a5b6cf] whitespace-pre-wrap">{{ tool.input }}</div>
                                    @if (tool.output) {
                                        <div class="mt-2 pt-2 border-t border-[#2d3546]">
                                            <div class="mb-1 text-gray-500 select-none">// Output</div>
                                            <div class="text-[#89ca78] whitespace-pre-wrap">{{ tool.output }}</div>
                                        </div>
                                    }
                                </div>
                            </div>
                        }
                    }

                    <!-- Main Content -->
                    <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed whitespace-pre-wrap">
                      {{ msg.content }}
                      @if (msg.isStreaming && !msg.reasoning) {
                        <span class="inline-block w-1.5 h-4 bg-[#478cbf] align-middle ml-0.5 animate-pulse"></span>
                      }
                    </div>

                  </div>
                </div>
              }
            }
          </div>
        </div>

        <!-- Input Area -->
        <div class="p-4 bg-[#202531]">
          <div class="max-w-3xl mx-auto relative bg-[#2d3546] rounded-xl shadow-lg border border-[#3b4458] focus-within:border-[#478cbf] focus-within:ring-1 focus-within:ring-[#478cbf]/50 transition-all duration-200">
            
            <textarea
              #messageInput
              [(ngModel)]="currentInput"
              (keydown.enter)="$event.preventDefault(); sendMessage()"
              placeholder="Ask Godoty a question..."
              class="w-full bg-transparent text-gray-200 placeholder-gray-500 text-sm px-4 py-3 pr-12 rounded-xl focus:outline-none resize-none max-h-48 overflow-y-auto"
              rows="1"
              style="min-height: 48px;"
              (input)="autoResize($event.target)"
            ></textarea>

            @if (isGeneratiing()) {
              <!-- Stop button when generating -->
              <button
                (click)="stopGeneration()"
                class="absolute right-2 bottom-2 p-1.5 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-all"
                title="Stop generation"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                  <path d="M5.25 3A2.25 2.25 0 003 5.25v9.5A2.25 2.25 0 005.25 17h9.5A2.25 2.25 0 0017 14.75v-9.5A2.25 2.25 0 0014.75 3h-9.5z" />
                </svg>
              </button>
            } @else {
              <!-- Send button when not generating -->
              <button
                (click)="sendMessage()"
                [disabled]="!currentInput()"
                class="absolute right-2 bottom-2 p-1.5 rounded-lg bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 disabled:bg-transparent disabled:text-gray-500 transition-all"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                  <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A2 2 0 005.635 9.75h5.736a.75.75 0 010 1.5H5.636a2 2 0 00-1.942 1.586l-1.414 4.925a.75.75 0 00.826.95 28.89 28.89 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                </svg>
              </button>
            }
          </div>
          <div class="text-center text-[10px] text-gray-600 mt-2 font-mono">
            Godoty can make mistakes. Check generated code in the Godot docs.
          </div>
        </div>

      </main>
    </div>
  `,
  styles: [`
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3b4458; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #4b556b; }
    
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes fadeInUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .animate-fade-in { animation: fadeIn 0.3s ease-out forwards; }
    .animate-fade-in-up { animation: fadeInUp 0.3s ease-out forwards; }
  `]
})
export class App implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  private chatService = inject(ChatService);
  private desktopService = inject(DesktopService);

  sidebarOpen = signal(true);
  currentInput = signal('');
  isGeneratiing = signal(false);
  private currentAbortController: AbortController | null = null;
  activeSessionId = signal<string | null>(null);
  isDraftMode = signal(false);

  metrics = signal<Metrics>({
    latency: 0,
    tokensPerSec: 0,
  });

  sessions = signal<Session[]>([]);
  messages = signal<Message[]>([]);
  godotStatus = signal<GodotStatus | null>(null);
  isGodotConnected = signal(false);

  constructor() {
    // Effect to scroll to bottom when messages change
    effect(() => {
      this.messages();
      setTimeout(() => this.scrollToBottom(), 0);
    });
  }

  ngOnInit() {
    this.loadSessions();

    // Set draft mode after loading sessions if no sessions exist
    setTimeout(() => {
      if (this.sessions().length === 0) {
        this.isDraftMode.set(true);
      }
    }, 100);

    // Subscribe to Godot Status
    this.desktopService.streamGodotStatus().subscribe(status => {
      this.godotStatus.set(status);
      this.isGodotConnected.set(status.state === 'connected');

      // If we have a project path, tell chat service
      if (status.project_path) {
        this.chatService.setProjectPath(status.project_path);
      }
    });

    // Subscribe to Project Metrics
    this.chatService.projectMetrics$.subscribe(metrics => {
      // Update global metrics if needed, or just use per-message metrics
    });
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  loadSessions() {
    this.chatService.listSessions().subscribe(sessions => {
      this.sessions.set(sessions);
      // Only auto-select if not in draft mode and no active session
      if (sessions.length > 0 && !this.activeSessionId() && !this.isDraftMode()) {
        this.selectSession(sessions[0].id);
      }
    });
  }

  selectSession(sessionId: string) {
    this.activeSessionId.set(sessionId);
    this.messages.set([]); // Clear current messages
    this.isDraftMode.set(false); // Exit draft mode when selecting a session

    this.chatService.getSession(sessionId).subscribe(sessionData => {
      // Assuming sessionData contains messages. If not, we might need another endpoint or the data structure is different.
      // Based on ChatService, getSession returns the session object. 
      // We might need to fetch history if it's not included. 
      // For now, let's assume we start empty or fetch if available.
      // Actually, standard ChatService usually doesn't return messages in listSessions, but getSession might.
      // Let's check if there are messages in the response.
      if (sessionData && sessionData.messages) {
        const mappedMessages: Message[] = sessionData.messages.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          timestamp: new Date(m.timestamp),
          toolCalls: m.toolCalls?.map((tc: any) => ({
            toolName: tc.name,
            input: JSON.stringify(tc.input),
            output: JSON.stringify(tc.result),
            status: tc.status === 'completed' ? 'success' : tc.status
          }))
        }));
        this.messages.set(mappedMessages);
      }
    });
  }

  deleteSession(sessionId: string, event: Event): void {
    event.stopPropagation(); // Prevent session selection when clicking delete

    // Confirmation dialog
    if (!confirm('Are you sure you want to delete this session? This action cannot be undone.')) {
      return;
    }

    this.chatService.deleteSession(sessionId).subscribe({
      next: (response) => {
        console.log('Session deleted:', response);

        // If the deleted session was active, clear the view
        if (this.activeSessionId() === sessionId) {
          this.activeSessionId.set(null);
          this.messages.set([]);
          this.isDraftMode.set(true);
        }

        // Reload session list
        this.loadSessions();
      },
      error: (error) => {
        console.error('Error deleting session:', error);
        alert('Failed to delete session: ' + (error.error?.message || error.message));
      }
    });
  }

  toggleSidebar() {
    this.sidebarOpen.update(v => !v);
  }

  createNewSession(): void {
    // Clear state and enter draft mode
    // Session will be created when first message is sent
    this.activeSessionId.set(null);
    this.messages.set([]);
    this.isDraftMode.set(true);
  }

  private extractTitleFromMessage(message: string): string {
    let title = message.trim();

    // Remove markdown code blocks
    title = title.replace(/^```[\w]*\s*/, '');
    title = title.replace(/```\s*$/, '');

    // Normalize whitespace
    title = title.replace(/\s+/g, ' ');

    // Truncate at 16 chars (word boundary) - matching backend
    if (title.length > 16) {
      const truncated = title.substring(0, 16).split(' ').slice(0, -1).join(' ');
      title = truncated.length > 8 ? truncated + '...' : title.substring(0, 16) + '...';
    }

    return title || 'New Session';
  }

  private async createSessionWithTitle(sessionId: string, title: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.chatService.createSession(sessionId, title).subscribe({
        next: (session) => {
          this.waitForSessionReady(session.id).then(() => {
            resolve();
          }).catch((error) => {
            console.error('Session creation failed:', error);
            reject(error);
          });
        },
        error: (error) => {
          console.error('Failed to create session:', error);
          reject(error);
        }
      });
    });
  }

  private waitForSessionReady(sessionId: string, maxAttempts = 10): Promise<void> {
    return new Promise((resolve, reject) => {
      let attempts = 0;

      const checkStatus = () => {
        attempts++;
        this.chatService.getSessionStatus(sessionId).subscribe({
          next: (status) => {
            if (status.ready) {
              resolve();
            } else if (attempts >= maxAttempts) {
              reject(new Error('Session initialization timeout'));
            } else {
              setTimeout(checkStatus, 500);
            }
          },
          error: () => {
            if (attempts >= maxAttempts) {
              reject(new Error('Failed to check session status'));
            } else {
              setTimeout(checkStatus, 500);
            }
          }
        });
      };

      checkStatus();
    });
  }

  private isSessionReady(sessionId: string): Promise<boolean> {
    return new Promise((resolve) => {
      this.chatService.getSessionStatus(sessionId).subscribe({
        next: (status) => resolve(status.ready),
        error: () => resolve(false)
      });
    });
  }

  autoResize(textarea: any) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch (err) { }
  }

  async sendMessage() {
    if (!this.currentInput().trim()) return;

    const userContent = this.currentInput();
    this.currentInput.set(''); // Clear input immediately

    // CRITICAL FIX: Add user message to UI immediately
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userContent,
      timestamp: new Date()
    };
    this.messages.update(msgs => [...msgs, userMsg]);

    try {
      let sessionId = this.activeSessionId();

      // Check if we're in draft mode - create session with message as title
      if (this.isDraftMode()) {
        const newSessionId = Date.now().toString();
        const title = this.extractTitleFromMessage(userContent);

        // Create session with meaningful title
        await this.createSessionWithTitle(newSessionId, title);

        // Exit draft mode and set active session
        sessionId = newSessionId;
        this.activeSessionId.set(sessionId);
        this.isDraftMode.set(false);

        // Refresh session list to show new session
        this.loadSessions();
      } else if (!sessionId) {
        // Fallback: No session and not in draft mode (shouldn't normally happen)
        this.createNewSession();
        return; // Exit early, user will need to send again
      }

      // For existing sessions, update title with new message content
      if (!this.isDraftMode() && sessionId) {
        const newTitle = this.extractTitleFromMessage(userContent);
        this.updateSessionTitle(sessionId, newTitle);
      }

      // Double-check session is ready
      const isReady = await this.isSessionReady(sessionId);
      if (!isReady) {
        await this.waitForSessionReady(sessionId);
      }

      // Send the actual message
      await this.sendActualMessage(userContent, sessionId);
    } catch (error) {
      console.error('Failed to send message:', error);
      // Show error to user by adding error message
      this.messages.update(msgs => {
        const updated = [...msgs];
        const errorMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `❌ Error: ${error instanceof Error ? error.message : 'Failed to send message'}`,
          timestamp: new Date(),
          isStreaming: false
        };
        return [...updated, errorMsg];
      });
      this.isGeneratiing.set(false);
    }
  }

  private async sendActualMessage(userContent: string, sessionId: string): Promise<void> {
    // 1. Add User Message (already added in sendMessage)
    this.isGeneratiing.set(true);

    // Create AbortController for cancellation
    this.currentAbortController = new AbortController();

    // 2. Prepare Assistant Stub
    const assistantId = (Date.now() + 1).toString();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      reasoning: '',
      timestamp: new Date(),
      isStreaming: true,
      toolCalls: []
    };

    this.messages.update(msgs => [...msgs, assistantMsg]);

    // 3. Stream Response
    try {
      const stream = this.chatService.sendMessageStream(
        sessionId,
        userContent,
        undefined,
        this.currentAbortController.signal
      );
      let startTime = Date.now();
      let tokenCount = 0;

      for await (const event of stream) {
        this.messages.update(msgs => msgs.map(m => {
          if (m.id !== assistantId) return m;

          const updated = { ...m };

          // Handle different event types with raw backend format
          if (event.type === 'data' && event.data?.text) {
            updated.content += event.data.text;
            tokenCount++; // Rough estimation
          } else if (event.type === 'text' && event.content) {
            updated.content += event.content;
            tokenCount++; // Rough estimation
          } else if (event.type === 'reasoning' && event.data?.text) {
            updated.reasoning = (updated.reasoning || '') + event.data.text;
          } else if (event.type === 'reasoning' && event.reasoning) {
            updated.reasoning = (updated.reasoning || '') + event.reasoning;
          } else if (event.type === 'tool_use' && event.data) {
            // Handle raw backend format for tool_use events
            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            const toolCallData: ToolCall = {
              toolName: event.data.tool_name || event.data.name || 'unknown',
              input: JSON.stringify(event.data.tool_input || event.data.input || {}),
              output: '',
              status: 'pending' // Default status
            };

            // Check if this tool call has a result
            if (event.data.result) {
              toolCallData.output = JSON.stringify(event.data.result, null, 2);
              toolCallData.status = 'success';
            }

            // Add new tool call
            updated.toolCalls = [...updated.toolCalls, toolCallData];
          } else if (event.type === 'tool_use' && event.toolCall) {
            // Ensure toolCalls array exists
            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            // Check if this is a new tool call or an update
            // Use index-based matching: find pending tool with same name, or add new
            let toolCallIndex = -1;

            // If event has an explicit index, use it
            if (event.toolCall.index !== undefined) {
              toolCallIndex = event.toolCall.index;
            } else {
              // Otherwise, find existing pending tool by name (for backward compat)
              toolCallIndex = updated.toolCalls.findIndex(
                tc => tc.toolName === event.toolCall.name && tc.status === 'pending'
              );
            }

            const toolCallData: ToolCall = {
              toolName: event.toolCall.name,
              input: JSON.stringify(event.toolCall.input || {}),
              output: '',
              status: 'pending' // Default status
            };

            // Map backend status to frontend status
            if (event.status === 'completed') {
              toolCallData.status = 'success';
            } else if (event.status === 'failed') {
              toolCallData.status = 'error';
            } else if (event.status === 'running') {
              toolCallData.status = 'pending';
            }

            // If tool has result, set output and mark as success (unless already failed)
            if (event.toolCall.result) {
              toolCallData.output = JSON.stringify(event.toolCall.result, null, 2);
              if (!event.status || event.status === 'completed') {
                toolCallData.status = 'success';
              }
            }

            if (toolCallIndex >= 0 && toolCallIndex < updated.toolCalls.length) {
              // Update existing tool call at the found index
              updated.toolCalls[toolCallIndex] = {
                ...updated.toolCalls[toolCallIndex],
                ...toolCallData
              };
            } else {
              // Add new tool call
              updated.toolCalls = [...updated.toolCalls, toolCallData];
            }
          } else if (event.type === 'metrics' && event.data?.metrics) {
            // Handle raw backend format for metrics events
            updated.metrics = {
              total_tokens: event.data.metrics.total_tokens || 0,
              input_tokens: event.data.metrics.input_tokens || 0,
              output_tokens: event.data.metrics.output_tokens || 0,
              estimated_cost: event.data.metrics.estimated_cost || 0,
              model_id: event.data.metrics.model_id || 'unknown'
            };
          } else if (event.type === 'metrics' && event.metrics) {
            // Store metrics for display (fallback for transformed format)
            updated.metrics = {
              total_tokens: event.metrics.total_tokens || 0,
              input_tokens: event.metrics.input_tokens || 0,
              output_tokens: event.metrics.output_tokens || 0,
              estimated_cost: event.metrics.estimated_cost || 0,
              model_id: event.metrics.model_id || 'unknown'
            };
          } else if (event.type === 'error') {
            updated.error = event.error || 'Unknown error occurred';
          } else if (event.type === 'done') {
            // Stream finished
            updated.isStreaming = false;
          }

          return updated;
        }));
      }

      // Calculate metrics
      const endTime = Date.now();
      const duration = endTime - startTime;
      this.metrics.set({
        latency: duration,
        tokensPerSec: tokenCount / (duration / 1000)
      });

    } catch (error: any) {
      console.error('Error sending message:', error);

      // Handle cancellation separately from errors
      if (error.name === 'AbortError') {
        console.log('Stream cancelled by user');
        this.messages.update(msgs => msgs.map(m => {
          if (m.id === assistantId) {
            return {
              ...m,
              content: m.content || '',
              isStreaming: false
            };
          }
          return m;
        }));
      } else {
        this.messages.update(msgs => msgs.map(m =>
          m.id === assistantId ? { ...m, content: m.content + '\n[Error generating response]' } : m
        ));
      }
    } finally {
      this.isGeneratiing.set(false);
      this.currentAbortController = null;
      this.messages.update(msgs => msgs.map(m =>
        m.id === assistantId ? { ...m, isStreaming: false } : m
      ));
    }
  }

  updateSessionTitle(sessionId: string, newTitle: string): void {
    this.chatService.updateSessionTitle(sessionId, newTitle).subscribe({
      next: (response) => {
        console.log('Session title updated:', response);
        // Update session in the local list
        this.sessions.update(sessions =>
          sessions.map(session =>
            session.id === sessionId
              ? { ...session, title: newTitle }
              : session
          )
        );
      },
      error: (error) => {
        console.error('Error updating session title:', error);
      }
    });
  }

  stopGeneration(): void {
    if (this.currentAbortController) {
      console.log('Stopping generation...');
      this.currentAbortController.abort();
      this.currentAbortController = null;
      this.isGeneratiing.set(false);
    }
  }
}
