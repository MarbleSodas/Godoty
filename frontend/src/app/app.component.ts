import { Component, signal, computed, effect, ViewChild, ElementRef, AfterViewChecked, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Message, Session } from './services/chat.service';
import { DesktopService } from './services/desktop.service';

interface SessionMetrics {
  totalTokens: number;
  sessionCost: number;
  projectTotalCost: number;
}

interface AgentConfig {
  projectPath: string;
  model: string;
  status: 'idle' | 'working' | 'stopped' | 'paused';
  showSettings: boolean;
  godotVersion: string;
  godotConnected: boolean;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="flex h-screen w-full bg-[#212529] text-slate-200 font-sans overflow-hidden selection:bg-[#478cbf] selection:text-white">
      
      <!-- Sidebar -->
      <aside class="w-72 flex-shrink-0 flex flex-col border-r border-[#363d4a] bg-[#212529]">
        <!-- Header / Logo -->
        <div class="p-4 border-b border-[#363d4a] flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded bg-[#478cbf] flex items-center justify-center shadow-lg shadow-blue-900/20">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h1 class="font-bold text-lg tracking-tight text-white">Godoty</h1>
          </div>
          
          <!-- Settings Toggle (Menu) -->
          <button (click)="toggleSettings()" class="p-2 rounded hover:bg-[#363d4a] text-slate-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>

        <!-- Session List (Takes remaining height) -->
        <div class="flex-1 overflow-y-auto p-2">
          <div class="px-2 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">History</div>
          
          <div class="space-y-1">
            @for (session of sessions(); track session.id) {
              <button 
                class="w-full text-left px-3 py-3 rounded-lg text-sm transition-all duration-200 group flex flex-col gap-1"
                [class.bg-[#363d4a]]="session.active"
                [class.text-white]="session.active"
                [class.text-slate-400]="!session.active"
                [class.hover:bg-[#2b303b]]="!session.active"
                [class.hover:text-slate-200]="!session.active"
                (click)="selectSession(session.id)">
                
                <span class="font-medium truncate">{{ session.title }}</span>
                <span class="text-[10px] opacity-60">{{ session.date | date:'shortTime' }}</span>
              </button>
            }
          </div>
        </div>

        <!-- Metrics Panel (Fixed at bottom of sidebar) -->
        <div class="p-4 bg-[#1d2125] border-t border-[#363d4a]">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Performance
          </div>
          
          <div class="space-y-3">
            <div class="flex justify-between items-baseline">
              <span class="text-[11px] text-slate-400">Session Cost</span>
              <span class="font-mono text-sm text-white">\${{ metrics().sessionCost.toFixed(4) }}</span>
            </div>
            <div class="w-full bg-[#2b303b] h-1 rounded-full overflow-hidden">
               <div class="bg-green-500 h-full rounded-full" [style.width.%]="(metrics().sessionCost * 1000) % 100"></div>
            </div>

            <div class="flex justify-between items-baseline">
               <span class="text-[11px] text-slate-400">Tokens</span>
               <span class="font-mono text-sm text-[#478cbf]">{{ metrics().totalTokens | number }}</span>
            </div>
             <div class="flex justify-between items-baseline pt-2 border-t border-[#363d4a]">
               <span class="text-[11px] text-slate-400">Project Total</span>
               <span class="font-mono text-sm text-slate-300">\${{ metrics().projectTotalCost.toFixed(2) }}</span>
            </div>
          </div>
        </div>
        
        <!-- Footer -->
        <div class="p-3 border-t border-[#363d4a] text-[10px] text-slate-500 flex justify-between bg-[#1a1d21]">
           <span [title]="config().projectPath" class="truncate max-w-[150px]">{{ config().projectPath.split('/').pop() || 'No Project' }}</span>
           <span class="flex items-center gap-1" [title]="config().godotConnected ? 'Connected to Godot' : 'Disconnected'">
             <span class="w-1.5 h-1.5 rounded-full" [class.bg-green-500]="config().godotConnected" [class.bg-red-500]="!config().godotConnected"></span>
             {{ config().godotVersion || 'v4.x' }}
           </span>
        </div>
      </aside>

      <!-- Main Chat Area -->
      <main class="flex-1 flex flex-col relative bg-[#1a1d21]">
        
        <!-- Settings Overlay (Configuration Menu) -->
        @if (config().showSettings) {
          <div class="absolute inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-start justify-end p-4">
            <div class="bg-[#2b303b] border border-[#363d4a] rounded-xl shadow-2xl w-80 p-4 animate-in fade-in slide-in-from-top-2">
              <div class="flex justify-between items-center mb-4 border-b border-[#363d4a] pb-2">
                <h3 class="font-bold text-white">Configuration</h3>
                <button (click)="toggleSettings()" class="text-slate-400 hover:text-white">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div class="space-y-4">
                <div>
                  <label class="block text-xs text-slate-400 mb-1">Project Path</label>
                  <input type="text" [value]="config().projectPath" disabled class="w-full bg-[#212529] border border-[#363d4a] rounded px-2 py-1.5 text-xs text-slate-300 font-mono opacity-75">
                </div>
                <div>
                  <label class="block text-xs text-slate-400 mb-1">Model</label>
                  <select class="w-full bg-[#212529] border border-[#363d4a] rounded px-2 py-1.5 text-xs text-white focus:ring-1 focus:ring-[#478cbf] outline-none">
                    <option>claude-3-5-sonnet</option>
                    <option>gpt-4o</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        }

        <!-- Top Bar (Minimal) -->
        <div class="h-14 border-b border-[#363d4a] flex items-center justify-between px-6 bg-[#212529]/50 backdrop-blur supports-[backdrop-filter]:bg-[#212529]/50 sticky top-0 z-10">
          <div class="flex items-center gap-2">
             <span class="text-sm font-medium text-slate-300">{{ getCurrentSessionTitle() }}</span>
          </div>
          <div class="flex items-center gap-4 text-slate-400">
             <button class="hover:text-white transition-colors text-xs uppercase tracking-wider font-medium">Export</button>
          </div>
        </div>

        <!-- Messages Container -->
        <div class="flex-1 overflow-y-auto p-4 md:p-8 space-y-6 scroll-smooth" #scrollContainer>
          
          <!-- Welcome Message -->
          @if (messages().length === 0) {
            <div class="flex flex-col items-center justify-center py-10 text-center opacity-60">
               <div class="w-12 h-12 rounded bg-[#363d4a] flex items-center justify-center mb-4">
                 <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
               </div>
               <h2 class="text-lg font-medium text-white">Godoty Agent Ready</h2>
               <p class="text-sm text-slate-400 max-w-md mt-2">
                 I have analyzed the project structure at <code>{{config().projectPath}}</code>. 
                 I can help you refactor GDScript, create new scenes, or debug signals.
               </p>
            </div>
          }

          @for (msg of messages(); track msg.id) {
            <div class="w-full max-w-3xl mx-auto flex gap-4 group" [class.flex-row-reverse]="msg.role === 'user'">
              
              <!-- Avatar -->
              <div class="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center"
                   [class.bg-[#478cbf]]="msg.role === 'assistant'"
                   [class.bg-slate-600]="msg.role === 'user'">
                 @if (msg.role === 'assistant') {
                   <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                 } @else {
                   <span class="text-xs font-bold text-white">YOU</span>
                 }
              </div>

              <!-- Content -->
              <div class="flex flex-col max-w-[85%]" [class.items-end]="msg.role === 'user'">
                <div class="relative px-5 py-3.5 rounded-2xl text-sm leading-relaxed shadow-sm"
                     [class.bg-[#2b303b]]="msg.role === 'assistant'"
                     [class.text-slate-200]="msg.role === 'assistant'"
                     [class.rounded-tl-none]="msg.role === 'assistant'"
                     [class.bg-[#3d4452]]="msg.role === 'user'"
                     [class.text-white]="msg.role === 'user'"
                     [class.rounded-tr-none]="msg.role === 'user'">
                  
                  <div class="whitespace-pre-wrap font-light">{{ msg.content }}</div>
                  
                  @if(msg.isStreaming) {
                    <span class="inline-block w-2 h-4 ml-1 bg-[#478cbf] animate-pulse align-middle"></span>
                  }
                </div>

                <!-- Message Metrics -->
                @if (!msg.isStreaming && msg.cost !== undefined) {
                  <div class="flex items-center gap-3 mt-1.5 px-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                     <div class="flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        <span>{{ msg.tokens }} tok</span>
                     </div>
                     <div class="flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                        <span>$</span>
                        <span>{{ msg.cost.toFixed(5) }}</span>
                     </div>
                  </div>
                }
              </div>
            </div>
          }

          <!-- Spacer for bottom scrolling -->
          <div class="h-24"></div>
        </div>

        <!-- Input Area -->
        <div class="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#1a1d21] via-[#1a1d21] to-transparent">
          <div class="max-w-3xl mx-auto bg-[#2b303b] border border-[#363d4a] rounded-xl shadow-2xl shadow-black/20 flex flex-col overflow-hidden focus-within:border-[#478cbf] transition-colors">
            
            <textarea 
              [(ngModel)]="userInput" 
              (keydown.enter)="onEnter($event)"
              [disabled]="config().status === 'working' && config().status !== 'stopped'"
              placeholder="Ask Godoty to generate code, analyze scenes, or optimize assets..."
              class="w-full bg-transparent border-0 text-white placeholder-slate-500 focus:ring-0 resize-none py-4 px-4 min-h-[60px] max-h-[200px] text-sm disabled:opacity-50"
              rows="1"
            ></textarea>
            
            <div class="flex items-center justify-between px-3 py-2 bg-[#2b303b] border-t border-[#363d4a]/50">
               <div class="flex items-center gap-2">
                 <button class="p-2 rounded hover:bg-[#363d4a] text-slate-400 hover:text-[#478cbf] transition-colors" title="Attach GDScript">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                 </button>
                 <!-- Additional attachment options could go here -->
               </div>
               
               <div class="flex items-center gap-3">
                 @if (config().status !== 'working') {
                    <span class="text-[10px] text-slate-500 font-mono hidden sm:inline">
                        {{ userInput().length }} chars
                    </span>
                    <button 
                        (click)="sendMessage()" 
                        [disabled]="!userInput().trim()"
                        class="bg-[#478cbf] hover:bg-[#3a7ca8] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-blue-900/20">
                        <span>Send</span>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                    </button>
                 } @else {
                    <button 
                        (click)="stopAgent()" 
                        class="bg-[#d63e3e] hover:bg-[#b32d2d] text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-red-900/20">
                        <span>Stop</span>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 fill-current" viewBox="0 0 20 20">
                          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd" />
                        </svg>
                    </button>
                 }
               </div>
            </div>
          </div>
          <div class="text-center mt-2">
            <p class="text-[10px] text-slate-600">Godoty can make mistakes. Review generated GDScript before running.</p>
          </div>
        </div>

      </main>
    </div>
  `,
  styles: [`
    /* Custom Scrollbar for that IDE feel */
    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    ::-webkit-scrollbar-track {
      background: #212529; 
    }
    ::-webkit-scrollbar-thumb {
      background: #363d4a; 
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: #478cbf; 
    }
    
    /* Animation utilities */
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes slideDown { from { transform: translateY(-10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
    
    .animate-in { animation: fadeIn 0.2s ease-out; }
    .slide-in-from-top-2 { animation: slideDown 0.2s ease-out; }
  `]
})
export class App implements AfterViewChecked, OnInit {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  // Signals for Reactive State
  userInput = signal('');
  messages = signal<Message[]>([]);

  // Session State
  sessions = signal<Session[]>([]);
  currentSessionId = signal<string | null>(null);

  config = signal<AgentConfig>({
    projectPath: '',
    model: 'claude-3-5-sonnet',
    status: 'idle',
    showSettings: false,
    godotVersion: '',
    godotConnected: false
  });

  metrics = signal<SessionMetrics>({
    totalTokens: 0,
    sessionCost: 0.00,
    projectTotalCost: 0.00
  });

  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService
  ) { }

  ngOnInit() {
    this.loadSessions();
    this.loadSystemInfo();
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch (err) { }
  }

  loadSystemInfo() {
    console.log('[App] Loading system info...');

    // First, fetch the current status via HTTP GET to get initial state
    this.desktopService.getGodotStatus().subscribe({
      next: (status) => {
        console.log('[App] Initial Godot status:', status);
        this.updateGodotConfig(status);
      },
      error: (err) => {
        console.error('[App] Error fetching initial Godot status:', err);
        // Set disconnected state on error
        this.config.update(c => ({
          ...c,
          godotConnected: false,
          godotVersion: ''
        }));
      }
    });

    // Then subscribe to real-time Godot status updates via SSE
    this.desktopService.streamGodotStatus().subscribe({
      next: (status) => {
        console.log('[App] SSE Godot status update:', status);
        this.updateGodotConfig(status);
      },
      error: (err) => {
        console.error('[App] SSE stream error:', err);
        // Fallback to disconnected state on error
        this.config.update(c => ({
          ...c,
          godotConnected: false
        }));
      }
    });
  }

  private updateGodotConfig(status: any) {
    const isConnected = status.state === 'connected';
    const version = status.godot_version || '';
    const path = status.project_path || '';

    console.log('[App] Updating config - Connected:', isConnected, 'Version:', version, 'Path:', path);

    this.config.update(c => ({
      ...c,
      godotConnected: isConnected,
      godotVersion: version,
      projectPath: path || c.projectPath
    }));
  }

  loadSessions() {
    this.chatService.listSessions().subscribe(sessions => {
      this.sessions.set(sessions);
      if (sessions.length > 0 && !this.currentSessionId()) {
        this.selectSession(sessions[0].id);
      } else if (sessions.length === 0) {
        this.createNewSession();
      }
    });
  }

  createNewSession() {
    const newId = 'session-' + Date.now();
    this.chatService.createSession(newId).subscribe(() => {
      this.loadSessions();
      this.selectSession(newId);
    });
  }

  selectSession(id: string) {
    this.currentSessionId.set(id);
    this.sessions.update(s => s.map(session => ({
      ...session,
      active: session.id === id
    })));
    // Load messages for this session if backend supported message history retrieval
    // For now we start fresh or would need an endpoint to get history
    this.messages.set([]);
  }

  getCurrentSessionTitle() {
    return this.sessions().find(s => s.active)?.title || 'New Session';
  }

  toggleSettings() {
    this.config.update(c => ({ ...c, showSettings: !c.showSettings }));
  }

  onEnter(event: Event) {
    event.preventDefault();
    this.sendMessage();
  }

  async sendMessage() {
    const text = this.userInput().trim();
    if (!text || this.config().status === 'working') return;

    const sessionId = this.currentSessionId();
    if (!sessionId) {
      this.createNewSession();
      return;
    }

    // 1. Add User Message
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
      tokens: 0,
      cost: 0
    };

    this.messages.update(msgs => [...msgs, userMsg]);
    this.userInput.set('');
    this.config.update(c => ({ ...c, status: 'working' }));

    // 2. Add Placeholder Assistant Message
    const aiMsgId = (Date.now() + 1).toString();
    const aiMsg: Message = {
      id: aiMsgId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      tokens: 0,
      cost: 0
    };
    this.messages.update(msgs => [...msgs, aiMsg]);

    try {
      // 3. Stream Response
      for await (const chunk of this.chatService.sendMessageStream(sessionId, text)) {
        // Update message content
        if (chunk.content) {
          this.messages.update(msgs => msgs.map(m => {
            if (m.id === aiMsgId) {
              return { ...m, content: m.content + chunk.content };
            }
            return m;
          }));
        }

        // Handle other event types if needed (e.g., metrics)
        if (chunk.metrics) {
          this.updateMetrics(chunk.metrics.tokens || 0, chunk.metrics.cost || 0);
        }
      }

      // Mark as done streaming
      this.messages.update(msgs => msgs.map(m => {
        if (m.id === aiMsgId) {
          return { ...m, isStreaming: false };
        }
        return m;
      }));

    } catch (err: any) {
      console.error('Chat error:', err);
      const errorMsg: Message = {
        id: (Date.now() + 2).toString(),
        role: 'system',
        content: 'Error: ' + err.message,
        timestamp: new Date()
      };
      this.messages.update(msgs => [...msgs, errorMsg]);
      // Remove the empty AI message if it failed immediately
      this.messages.update(msgs => msgs.filter(m => m.id !== aiMsgId || m.content !== ''));
    } finally {
      this.config.update(c => ({ ...c, status: 'idle' }));
    }
  }

  stopAgent() {
    this.config.update(c => ({ ...c, status: 'stopped' }));
    // Implement stop logic with backend if supported
  }

  updateMetrics(tokens: number, cost: number) {
    this.metrics.update(m => ({
      totalTokens: m.totalTokens + tokens,
      sessionCost: m.sessionCost + cost,
      projectTotalCost: m.projectTotalCost + cost
    }));
  }
}
