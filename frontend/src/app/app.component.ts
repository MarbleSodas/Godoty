import { Component, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy, model, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

// Import services
import { ConfigService, AgentConfig, AvailableModel } from './services/config.service';
import { SessionService, Session, Message } from './services/session.service';
import { ChatService, ExecutionPlan } from './services/chat.service';
import { DesktopService, GodotStatus, DetailedConnectionStatus } from './services/desktop.service';
import { MetricsService, SessionMetrics, ProjectMetrics } from './services/metrics.service';

// Import utilities
import { EnvironmentDetector } from './utils/environment';

// Import preserved components
import { SettingsComponent } from './components/settings/settings.component';
import { ExecutionPlanComponent } from './components/execution/execution-plan.component';

// Import heroicons
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import {
  heroBars3,
  heroCog6Tooth,
  heroDocumentText,
  heroClock,
  heroCurrencyDollar,
  heroChartBar,
  heroHome,
  heroChatBubbleLeftRight,
  heroUsers,
  heroSparkles,
  heroArrowDown
} from '@ng-icons/heroicons/outline';
import {
  heroPencilSquareSolid,
  heroPlusCircleSolid,
  heroXMarkSolid,
  heroPlaySolid,
  heroStopSolid,
  heroChevronRightSolid,
  heroChartBarSolid,
  heroPaperAirplaneSolid
} from '@ng-icons/heroicons/solid';

// --- Main App Component ---

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, SettingsComponent, ExecutionPlanComponent, NgIconComponent],
  providers: [
    provideIcons({
      heroBars3,
      heroCog6Tooth,
      heroDocumentText,
      heroClock,
      heroCurrencyDollar,
      heroChartBar,
      heroHome,
      heroChatBubbleLeftRight,
      heroUsers,
      heroSparkles,
      heroArrowDown,
      heroPencilSquareSolid,
      heroPlusCircleSolid,
      heroXMarkSolid,
      heroPlaySolid,
      heroStopSolid,
      heroChevronRightSolid,
      heroChartBarSolid,
      heroPaperAirplaneSolid
    })
  ],
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
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
              <circle cx="9" cy="13" r="1.5" />
              <circle cx="15" cy="13" r="1.5" />
            </svg>
            <span>GODOTY</span>
          </div>
          <button (click)="createNewSession(); $event.preventDefault()" class="p-1.5 hover:bg-[#2d3546] rounded-md transition-colors text-gray-400 hover:text-white" title="New Chat">
            <ng-icon name="heroPlusCircleSolid" class="w-5 h-5" />
          </button>
        </div>

        <div class="flex-1 overflow-y-auto py-2">
          <div class="px-4 pb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">History</div>
          @for (session of sessions(); track session.id) {
            <button
              (click)="selectSession(session.id); $event.preventDefault()"
              class="w-full text-left px-4 py-3 text-sm truncate hover:bg-[#2d3546] transition-colors border-l-2"
              [class.border-[#478cbf]]="activeSessionId() === session.id"
              [class.bg-[#262c3b]]="activeSessionId() === session.id"
              [class.text-white]="activeSessionId() === session.id"
              [class.text-gray-400]="activeSessionId() !== session.id"
              [class.border-transparent]="activeSessionId() !== session.id"
            >
              {{ session.title }}
            </button>
          }
        </div>

        <div class="p-4 border-t border-[#2d3546] flex items-center space-x-3">
          <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-[#478cbf] to-cyan-400 flex items-center justify-center text-xs font-bold text-white">
            GD
          </div>
          <div class="text-sm">
            <div class="font-medium text-gray-200">GameDev User</div>
            <div class="text-xs text-gray-500">{{ projectMetrics().totalSessions }} Sessions</div>
          </div>
        </div>
      </aside>

      <!-- Main Content -->
      <main class="flex-1 flex flex-col relative min-w-0">

        <!-- Header -->
        <header class="h-14 border-b border-[#2d3546] bg-[#202531]/95 backdrop-blur flex items-center justify-between px-4 z-10 sticky top-0">
          <div class="flex items-center">
            <button (click)="toggleSidebar()" class="mr-3 p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors">
              <ng-icon name="heroBars3" class="w-5 h-5" />
            </button>
            <div class="flex flex-col">
              <span class="font-semibold text-gray-200 text-sm">
                Godoty {{ godotStatus().godot_version || 'Assistant' }}
              </span>
              <span class="text-[10px] flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full animate-pulse"
                      [class.bg-green-500]="godotStatus().state === 'connected'"
                      [class.bg-yellow-500]="godotStatus().state === 'connecting'"
                      [class.bg-red-500]="godotStatus().state === 'error'"
                      [class.bg-gray-500]="godotStatus().state === 'disconnected' || !godotStatus().state"></span>
                <span [class.text-green-400]="godotStatus().state === 'connected'"
                      [class.text-yellow-400]="godotStatus().state === 'connecting'"
                      [class.text-red-400]="godotStatus().state === 'error'"
                      [class.text-gray-400]="godotStatus().state === 'disconnected' || !godotStatus().state">
                  {{ getHeaderStatusText() }}
                </span>
              </span>
            </div>
          </div>

          <!-- Metrics Panel -->
          <div class="flex items-center gap-4">
            <!-- Metrics Display -->
            <div class="flex items-center gap-4 text-xs font-mono text-gray-500 bg-[#1a1e29] px-3 py-1.5 rounded border border-[#2d3546]">
              <div class="flex items-center gap-1.5" title="Generation Latency">
                <ng-icon name="heroClock" class="w-3 h-3" />
                <span>{{ currentMetrics().generationTimeMs || 0 }}ms</span>
              </div>
              <div class="w-px h-3 bg-[#2d3546]"></div>
              <div class="flex items-center gap-1.5" title="Total Tokens">
                <ng-icon name="heroChartBar" class="w-3 h-3" />
                <span>{{ currentMetrics().totalTokens || 0 }}</span>
              </div>
              <div class="w-px h-3 bg-[#2d3546]"></div>
              <div class="flex items-center gap-1.5" title="Session Cost">
                <ng-icon name="heroCurrencyDollar" class="w-3 h-3" />
                <span>{{ (currentMetrics().sessionCost || 0).toFixed(4) }}</span>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center gap-2">
              <button (click)="toggleSettings()" class="p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors" title="Settings">
                <ng-icon name="heroCog6Tooth" class="w-5 h-5" />
              </button>
              @if (currentPlan()) {
                <button (click)="toggleTaskSidebar()" class="p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors" title="Execution Plan">
                  <ng-icon name="heroDocumentText" class="w-5 h-5" />
                </button>
              }
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
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
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
                                        [class.text-green-200]="tool.status === 'success'">
                                        {{ tool.status }}
                                    </span>
                                </div>
                                <div class="p-3 text-gray-400">
                                    <div class="mb-1 text-gray-500 select-none">// Input</div>
                                    <div class="mb-2 text-[#a5b6cf]">{{ tool.input }}</div>
                                    @if (tool.output) {
                                        <div class="mt-2 pt-2 border-t border-[#2d3546]">
                                            <div class="mb-1 text-gray-500 select-none">// Output</div>
                                            <div class="text-[#89ca78]">{{ tool.output }}</div>
                                        </div>
                                    }
                                </div>
                            </div>
                        }
                    }

                    <!-- Main Content -->
                    <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed">
                      {{ msg.content }}
                      @if (msg.isStreaming) {
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
              [disabled]="!isConfigured()"
            ></textarea>

            <button
              (click)="sendMessage()"
              [disabled]="!currentInput().trim() || !isConfigured() || isGenerating()"
              class="absolute right-2 bottom-2 p-1.5 rounded-lg bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 disabled:bg-transparent disabled:text-gray-500 transition-all"
            >
              @if (isGenerating()) {
                <ng-icon name="heroStopSolid" class="w-5 h-5 animate-spin" />
              } @else {
                <ng-icon name="heroPaperAirplaneSolid" class="w-5 h-5" />
              }
            </button>
          </div>
          @let configMessage = getConfigurationMessage();
          @if (!isConfigured() || configMessage.type === 'info') {
            <div class="text-center text-[10px] mt-2 font-mono"
                 [class]="configMessage.type === 'error' ? 'text-red-400' :
                            configMessage.type === 'warning' ? 'text-yellow-400' :
                            'text-blue-400'">
              {{ configMessage.message }}
            </div>
          } @else {
            <div class="text-center text-[10px] text-gray-600 mt-2 font-mono">
              Godoty can make mistakes. Check generated code in the Godot docs.
            </div>
          }
        </div>

      </main>

      <!-- Settings Modal -->
      @if (showSettings()) {
        <div class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4" (click)="closeSettings()">
          <div class="animate-in slide-in-from-top-2 w-[500px]" (click)="$event.stopPropagation()">
            <app-settings (close)="closeSettings()"></app-settings>
          </div>
        </div>
      }

      <!-- Execution Plan Sidebar -->
      @if (currentPlan() && showTaskSidebar()) {
        <app-execution-plan
          [plan]="currentPlan()"
          [isOpen]="showTaskSidebar()"
          [isMobile]="isMobile()"
          (close)="closeTaskSidebar()"
        ></app-execution-plan>
      }
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

    .animate-in { animation: fadeIn 0.2s ease-out; }
    .slide-in-from-top-2 { animation: slideDown 0.2s ease-out; }
  `]
})
export class App implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  @ViewChild('messageInput') private messageInput!: ElementRef;

  // Signals for reactive state
  sidebarOpen = signal(true);
  currentInput = signal('');
  isGenerating = signal(false);
  activeSessionId = signal<string | null>(null);

  // Data signals
  sessions = signal<Session[]>([]);
  messages = signal<Message[]>([]);
  currentMetrics = signal<SessionMetrics>({
    totalTokens: 0,
    sessionCost: 0,
    toolCalls: 0
  });
  projectMetrics = signal<ProjectMetrics>({
    totalCost: 0,
    totalTokens: 0,
    totalSessions: 0
  });
  godotStatus = signal<GodotStatus>({
    state: 'disconnected'
  });
  detailedConnectionStatus = signal<DetailedConnectionStatus | null>(null);
  agentConfig = signal<AgentConfig>({
    projectPath: '',
    agentModel: '',
    openRouterKey: '',
    status: 'idle',
    showSettings: false,
    showTaskSidebar: false,
    godotVersion: '',
    godotConnected: false,
    connectionState: 'disconnected',
    mode: 'planning',
    showFullPath: false
  });
  currentPlan = signal<ExecutionPlan | null>(null);
  backendHasApiKey = signal<boolean>(false);

  private subscriptions: Subscription[] = [];

  constructor(
    private configService: ConfigService,
    private sessionService: SessionService,
    private chatService: ChatService,
    private desktopService: DesktopService,
    private metricsService: MetricsService
  ) {}

  ngOnInit() {
    this.setupSubscriptions();
    this.loadInitialData();
  }

  ngOnDestroy() {
    this.subscriptions.forEach(sub => sub.unsubscribe());
  }

  /**
   * Update connection state from Godot status and sync to config service
   * @param status Godot status from SSE stream
   */
  private updateConnectionStateFromStatus(status: GodotStatus): void {
    // Sync Godot connection state to config service
    const isConnected = status.state === 'connected';
    this.configService.setConnectionState(status.state as 'connected' | 'disconnected' | 'connecting' | 'error');
    if (status.godot_version) {
      this.configService.setGodotConnection(isConnected, status.godot_version);
    }

    // Sync Godot-detected project path to services if available and not already configured
    if (isConnected && status.project_path) {
      const currentConfigPath = this.configService.getProjectPath();
      // Only auto-set if user hasn't manually configured a path
      if (!currentConfigPath || currentConfigPath.trim() === '') {
        this.sessionService.setProjectPath(status.project_path);
        this.configService.setProjectPath(status.project_path);
      } else if (currentConfigPath !== status.project_path) {
        // User has a configured path, but also sync Godot path to session service as fallback
        this.sessionService.setProjectPath(status.project_path);
      }
    }
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  private setupSubscriptions(): void {
    // Config subscription
    this.subscriptions.push(
      this.configService.config.subscribe(config => {
        this.agentConfig.set(config);
      })
    );

    // Sessions subscription
    this.subscriptions.push(
      this.sessionService.activeSessions.subscribe(sessions => {
        this.sessions.set(sessions);
      })
    );

    // Current session subscription
    this.subscriptions.push(
      this.sessionService.currentSessionId.subscribe(sessionId => {
        this.activeSessionId.set(sessionId);
        if (sessionId) {
          this.loadSessionMessages(sessionId);
        } else {
          this.messages.set([]);
        }
      })
    );

    // Messages subscription
    this.subscriptions.push(
      this.sessionService.messages.subscribe(messageMap => {
        const currentSessionId = this.activeSessionId();
        if (currentSessionId) {
          const sessionMessages = messageMap.get(currentSessionId) || [];
          this.messages.set(sessionMessages);
          this.updateCurrentMetrics(sessionMessages);
        }
      })
    );

    // Godot status subscription - sync to both local state and config service
    // Use streaming SSE for real-time updates
    this.subscriptions.push(
      this.desktopService.streamGodotStatus().subscribe({
        next: (status: GodotStatus) => {
          console.log('[AppComponent] Godot status update received:', status);
          console.log('[AppComponent] Project name from SSE:', status.project_name);
          console.log('[AppComponent] Connection state from SSE:', status.state);
          console.log('[AppComponent] Godot version from SSE:', status.godot_version);
          console.log('[AppComponent] Project path from SSE:', status.project_path);

          // Update local signal
          this.godotStatus.set(status);
          console.log('[AppComponent] Godot status signal updated');

          // Update connection state and sync to config service
          this.updateConnectionStateFromStatus(status);
          console.log('[AppComponent] Connection state updated and synced');
        },
        error: (error) => {
          console.error('[AppComponent] Error receiving Godot status:', error);
          console.error('[AppComponent] SSE subscription error details:', error);
        },
        complete: () => {
          console.log('[AppComponent] Godot status subscription completed');
        }
      })
    );

    // Enhanced detailed connection status polling for comprehensive monitoring
    this.subscriptions.push(
      this.desktopService.pollConnectionStatus(3000).subscribe(detailedStatus => {
        this.detailedConnectionStatus.set(detailedStatus);

        // Use detailed status for enhanced project auto-configuration
        // Check both agent and monitor for project path, with priority to agent
        const projectPath = detailedStatus.agent.project_info?.project_path || detailedStatus.monitor.project_path;
        if (detailedStatus.integration_available && projectPath) {
          const currentConfigPath = this.configService.getProjectPath();
          if (!currentConfigPath || currentConfigPath.trim() === '') {
            this.sessionService.setProjectPath(projectPath);
            this.configService.setProjectPath(projectPath);
          }
        }

        // Log connection quality metrics for debugging
        console.log('[App] Detailed connection status:', {
          monitorRunning: detailedStatus.monitor.running,
          agentConnected: detailedStatus.agent.connected,
          integrationAvailable: detailedStatus.integration_available,
          timestamp: detailedStatus.timestamp
        });
      })
    );

    // API key status subscription - track backend API key
    this.subscriptions.push(
      this.configService.apiKeyStatus.subscribe(status => {
        if (status) {
          this.backendHasApiKey.set(status.hasKey);
        } else {
          this.backendHasApiKey.set(false);
        }
      })
    );

    // Project metrics subscription - check if it exists
    if (this.metricsService.projectMetrics) {
      this.subscriptions.push(
        this.metricsService.projectMetrics.subscribe(metrics => {
          if (metrics) {
            this.projectMetrics.set(metrics);
          }
        })
      );
    }

    // Setup execution plan tracking from messages
    this.subscriptions.push(
      this.sessionService.messages.subscribe(messageMap => {
        const currentSessionId = this.activeSessionId();
        if (currentSessionId) {
          const sessionMessages = messageMap.get(currentSessionId) || [];
          // Find the most recent assistant message with a plan
          for (let i = sessionMessages.length - 1; i >= 0; i--) {
            if (sessionMessages[i].role === 'assistant' && sessionMessages[i].plan) {
              this.currentPlan.set(sessionMessages[i].plan);
              return;
            }
          }
          this.currentPlan.set(null);
        }
      })
    );
  }

  private loadInitialData(): void {
    this.sessionService.initialize();
    // Godot status streaming is already set up in setupSubscriptions()
  }

  private loadSessionMessages(sessionId: string): void {
    const messageMap = this.sessionService.messages.value;
    const sessionMessages = messageMap.get(sessionId) || [];
    this.messages.set(sessionMessages);
    this.updateCurrentMetrics(sessionMessages);
  }

  private updateCurrentMessages(messages: Message[]): void {
    this.messages.set(messages);
    this.updateCurrentMetrics(messages);
  }

  private updateCurrentMetrics(messages: Message[]): void {
    const totalTokens = messages.reduce((sum, msg) => sum + (msg.tokens || 0), 0);
    const sessionCost = messages.reduce((sum, msg) => sum + (msg.cost || 0), 0);
    const toolCalls = messages.reduce((sum, msg) => sum + (msg.toolCalls?.length || 0), 0);
    const generationTimeMs = messages.length > 0 ? messages[messages.length - 1].generationTimeMs : 0;

    this.currentMetrics.set({
      totalTokens,
      sessionCost,
      toolCalls,
      generationTimeMs
    });
  }

  // UI Methods
  toggleSidebar() {
    this.sidebarOpen.update(v => !v);
  }

  toggleSettings() {
    this.configService.toggleSettings();
  }

  toggleTaskSidebar() {
    this.configService.toggleTaskSidebar();
  }

  closeSettings() {
    this.configService.hideSettingsPanel();
  }

  closeTaskSidebar() {
    this.configService.hideTaskSidebarPanel();
  }

  showSettings() {
    return this.agentConfig().showSettings;
  }

  showTaskSidebar() {
    return this.agentConfig().showTaskSidebar;
  }

  isMobile(): boolean {
    return window.innerWidth < 768;
  }

  isConfigured(): boolean {
    const config = this.agentConfig();
    const godotStatus = this.godotStatus();

    // API key can be in frontend localStorage OR backend .env
    const hasFrontendKey = !!(config.openRouterKey);
    const hasBackendKey = this.backendHasApiKey();
    const hasApiKey = hasFrontendKey || hasBackendKey;

    // Log critical API key status for desktop mode debugging
    if (EnvironmentDetector.isDesktopMode() && !hasApiKey) {
      console.error('[AppComponent] Critical: No API key found - Frontend:', hasFrontendKey, 'Backend:', hasBackendKey);
    }

    // Project path can be manually configured OR auto-detected from Godot
    const hasProjectPath = !!(config.projectPath) || !!(godotStatus.project_path);

    const hasModel = !!config.agentModel;

    // Only validate core configuration items, not connection state
    return hasApiKey && hasProjectPath && hasModel;
  }

  isReadyForUse(): boolean {
    // Additional method for full readiness including connection
    return this.isConfigured() && this.agentConfig().connectionState === 'connected';
  }

  // Session Methods
  async selectSession(sessionId: string) {
    await this.sessionService.selectSession(sessionId);
  }

  async createNewSession() {
    await this.sessionService.createSession();
  }

  // Chat Methods
  async sendMessage() {
    const content = this.currentInput().trim();
    if (!content || !this.isConfigured() || this.isGenerating()) return;

    this.currentInput.set('');

    // Ensure we have an active session
    let currentSessionId = this.activeSessionId();
    if (!currentSessionId) {
      currentSessionId = await this.sessionService.createSession();
    }

    if (currentSessionId) {
      this.isGenerating.set(true);
      this.processMessageStream(currentSessionId, content);
    }
  }

  private async processMessageStream(sessionId: string, message: string): Promise<void> {
    let userMessageId: string | null = null;
    let assistantMessageId: string | null = null;

    try {
      const config = this.agentConfig();

      // Generate title from first 20 characters of initial message
      await this.generateAndUpdateSessionTitle(sessionId, message);

      // Add user message immediately
      userMessageId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const userMessage: Message = {
        id: userMessageId,
        role: 'user',
        content: message,
        timestamp: new Date(),
        tokens: 0
      };
      this.sessionService.addMessage(sessionId, userMessage);

      // Create assistant message for streaming
      assistantMessageId = `assistant-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const assistantMessage: Message = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
        toolCalls: [],
        tokens: 0
      };
      this.sessionService.addMessage(sessionId, assistantMessage);

      const responseGenerator = this.chatService.sendMessageStream(sessionId, message, config.mode);

      for await (const event of responseGenerator) {
        await this.handleStreamingEvent(sessionId, assistantMessageId, event);
      }
    } catch (error) {
      console.error('Error sending message:', error);

      // Add error message if assistant message exists
      if (assistantMessageId) {
        this.sessionService.updateMessage(sessionId, assistantMessageId, {
          content: 'Sorry, I encountered an error while processing your message. Please try again.',
          isStreaming: false
        });
      }
    } finally {
      // Finalize streaming state
      if (assistantMessageId) {
        this.sessionService.updateMessage(sessionId, assistantMessageId, {
          isStreaming: false
        });
      }
      this.isGenerating.set(false);
    }
  }

  private async handleStreamingEvent(sessionId: string, messageId: string, event: any): Promise<void> {
    switch (event.type) {
      case 'text':
        // Append text content to assistant message
        const currentMessage = this.sessionService.getMessage(sessionId, messageId);
        if (currentMessage) {
          this.sessionService.updateMessage(sessionId, messageId, {
            content: currentMessage.content + (event.data.content || '')
          });
        }
        break;

      case 'tool_use':
        // Add tool call to message
        this.addToolCallToMessage(sessionId, messageId, event.data);
        break;

      case 'tool_result':
        // Update tool call with result
        this.updateToolCallWithResult(sessionId, messageId, event.data);
        break;

      case 'plan_created':
        // Add execution plan to message
        this.sessionService.updateMessage(sessionId, messageId, {
          plan: event.data
        });
        break;

      case 'metadata':
        // Update tokens, cost, and other metrics
        this.updateMessageMetadata(sessionId, messageId, event.data);
        break;

      case 'error':
        // Handle error events
        this.sessionService.updateMessage(sessionId, messageId, {
          content: (event.data?.message || 'An error occurred') + '\n\n' +
                   (this.sessionService.getMessage(sessionId, messageId)?.content || '')
        });
        break;

      default:
        console.log('Unhandled event type:', event.type, event);
    }
  }

  private addToolCallToMessage(sessionId: string, messageId: string, toolData: any): void {
    const currentMessage = this.sessionService.getMessage(sessionId, messageId);
    if (!currentMessage || !currentMessage.toolCalls) return;

    const toolCall = {
      id: toolData.id || `tool-${Date.now()}`,
      name: toolData.name || 'unknown',
      input: toolData.input || {},
      status: 'pending',
      result: null,
      timestamp: new Date()
    };

    this.sessionService.updateMessage(sessionId, messageId, {
      toolCalls: [...currentMessage.toolCalls, toolCall]
    });
  }

  private updateToolCallWithResult(sessionId: string, messageId: string, toolData: any): void {
    const currentMessage = this.sessionService.getMessage(sessionId, messageId);
    if (!currentMessage || !currentMessage.toolCalls) return;

    const updatedToolCalls = currentMessage.toolCalls.map(toolCall => {
      if (toolCall.id === toolData.id || toolCall.name === toolData.name) {
        return {
          ...toolCall,
          status: toolData.success ? 'success' : 'failed',
          result: toolData.result || toolData.error || 'No result available'
        };
      }
      return toolCall;
    });

    this.sessionService.updateMessage(sessionId, messageId, {
      toolCalls: updatedToolCalls
    });
  }

  private updateMessageMetadata(sessionId: string, messageId: string, metadata: any): void {
    const updates: Partial<Message> = {};

    if (metadata.tokens !== undefined) updates.tokens = metadata.tokens;
    if (metadata.prompt_tokens !== undefined) updates.promptTokens = metadata.prompt_tokens;
    if (metadata.completion_tokens !== undefined) updates.completionTokens = metadata.completion_tokens;
    if (metadata.cost !== undefined) updates.cost = metadata.cost;
    if (metadata.model_name !== undefined) updates.modelName = metadata.model_name;
    if (metadata.generation_time_ms !== undefined) updates.generationTimeMs = metadata.generation_time_ms;

    if (Object.keys(updates).length > 0) {
      this.sessionService.updateMessage(sessionId, messageId, updates);
    }
  }

  private async generateAndUpdateSessionTitle(sessionId: string, firstMessage: string): Promise<void> {
    // Generate title from first 20 characters
    let title = firstMessage.trim().slice(0, 20);
    if (firstMessage.trim().length > 20) {
      title += '...';
    }

    // Handle edge cases
    if (!title || title.trim() === '') {
      title = 'New Session';
    }

    // Update session title in frontend
    this.sessionService.updateSessionMetadata(sessionId, { title });

    // Update session title in backend (optional, for persistence)
    try {
      await this.chatService.updateSessionTitle(sessionId, title);
    } catch (error) {
      console.warn('Failed to update session title on backend:', error);
      // Don't fail the whole process if title update fails
    }
  }

  // Utility Methods
  autoResize(textarea: any) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  /**
   * Get project display name with enhanced logic prioritizing SSE project_name field
   */
  getProjectDisplayName(): string {
    const status = this.godotStatus();
    console.log('[Header] getProjectDisplayName called with status:', status);

    // PRIORITY: Use explicit project_name field from enhanced SSE
    if (status.project_name) {
      console.log('[Header] Using project_name from SSE:', status.project_name);
      return status.project_name;
    }

    // FALLBACK: Extract from project_settings.name
    if (status.project_settings?.name) {
      console.log('[Header] Using project_settings.name:', status.project_settings.name);
      return status.project_settings.name;
    }

    // FALLBACK: Extract from project_path
    if (status.project_path) {
      const name = this.getFolderNameFromPath(status.project_path);
      console.log('[Header] Using project_path to extract name:', name);
      return name;
    }

    console.log('[Header] No project information available');
    return 'Unknown Project';
  }

  /**
   * Get header status text based on Godot connection state
   */
  getHeaderStatusText(): string {
    const state = this.godotStatus().state;
    const projectPath = this.godotStatus().project_path;
    const projectName = this.godotStatus().project_name;

    console.log('[Header] getHeaderStatusText called:', { state, projectPath, projectName });

    switch (state) {
      case 'connected':
        const displayName = this.getProjectDisplayName();
        console.log('[Header] Connected - using display name:', displayName);
        return projectPath || projectName ? `Connected: ${displayName}` : 'Godot Connected';
      case 'connecting':
        return 'Connecting to Godot...';
      case 'error':
        return 'Connection Error';
      case 'disconnected':
        return 'Godot Disconnected';
      default:
        return 'No Godot Connection';
    }
  }

  /**
   * Extract folder name from full path
   */
  private getFolderNameFromPath(fullPath: string): string {
    if (!fullPath) return '';

    // Handle both Unix (/path/to/project) and Windows (C:\path\to\project) paths
    const parts = fullPath.split(/[/\\]/).filter(Boolean);
    return parts[parts.length - 1] || fullPath;
  }

  /**
   * Toggle show full path setting
   */
  toggleShowFullPath(): void {
    this.configService.toggleShowFullPath();
  }

  scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }

  /**
   * Get configuration message with type classification
   */
  getConfigurationMessage(): { message: string; type: 'error' | 'warning' | 'info' } {
    const config = this.agentConfig();
    const godotStatus = this.godotStatus();
    const hasApiKey = !!(config.openRouterKey) || this.backendHasApiKey();
    const hasProjectPath = !!(config.projectPath) || !!(godotStatus.project_path);

    // Check in order of importance
    if (!hasApiKey) {
      return { message: 'Please configure OpenRouter API key in settings or .env file', type: 'error' };
    }

    if (!config.agentModel) {
      return { message: 'Please select an AI model in settings', type: 'error' };
    }

    // Only show project path error if Godot is not connected and no manual path
    if (!hasProjectPath && config.connectionState === 'disconnected') {
      return { message: 'Please select a Godot project path in settings or connect to Godot Editor', type: 'warning' };
    }

    // Connection states should be info messages, not errors
    if (config.connectionState === 'disconnected') {
      return { message: 'Waiting for Godot Editor connection. Please open your project in Godot with the Godoty plugin enabled', type: 'info' };
    }

    if (config.connectionState === 'connecting') {
      return { message: 'Connecting to Godot Editor...', type: 'info' };
    }

    if (config.connectionState === 'error') {
      return { message: 'Error connecting to Godot Editor. Please check your plugin installation', type: 'error' };
    }

    return { message: 'Configuration complete', type: 'info' };
  }
}