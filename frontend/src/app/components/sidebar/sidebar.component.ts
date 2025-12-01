import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { SessionService, Session } from '../../services/session.service';
import { MetricsService, SessionMetrics, ProjectMetrics } from '../../services/metrics.service';
import { ChatService } from '../../services/chat.service';
import { ConfigService } from '../../services/config.service';

import { SessionItemComponent } from './session-item.component';
import { MetricsPanelComponent } from './metrics-panel.component';

// Import heroicons
import { NgIconComponent, provideIcons } from '@ng-icons/core';
import {
  heroAcademicCap,
  heroPlusCircle,
  heroChevronRight,
  heroHome,
  heroChatBubbleLeftRight,
  heroDocumentText,
  heroUsers,
  heroSparkles,
  heroArrowPath,
  heroExclamationTriangle
} from '@ng-icons/heroicons/outline';
import {
  heroPlusCircleSolid
} from '@ng-icons/heroicons/solid';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule, SessionItemComponent, MetricsPanelComponent, NgIconComponent],
  providers: [
    provideIcons({
      heroAcademicCap,
      heroPlusCircle,
      heroChevronRight,
      heroHome,
      heroChatBubbleLeftRight,
      heroDocumentText,
      heroUsers,
      heroSparkles,
      heroArrowPath,
      heroExclamationTriangle,
      heroPlusCircleSolid
    })
  ],
  template: `
    <div class="sidebar-container">
      <!-- Sidebar Header -->
      <div class="sidebar-header">
        <div class="header-content">
          <h2 class="app-title">
            <ng-icon name="heroAcademicCap" class="w-5 h-5" />
            Godoty
          </h2>
          <button
            class="new-session-button"
            (click)="createNewSession()"
            [disabled]="isCreatingSession"
            title="Create new session"
          >
            @if (isCreatingSession) {
              <ng-icon name="heroArrowPath" class="w-4 h-4 animate-spin" />
            } @else {
              <ng-icon name="heroPlusCircleSolid" class="w-4 h-4" />
            }
            <span class="button-text">{{ isCreatingSession ? 'Creating...' : 'New Session' }}</span>
          </button>
        </div>

        <!-- Connection Status -->
        <div class="connection-status" [class]="getConnectionStatusClass()">
          <div class="status-dot"></div>
          <span class="status-text">{{ getConnectionStatusText() }}</span>
        </div>
      </div>

      <!-- Sidebar Content -->
      <div class="sidebar-content">
        <!-- Tabs -->
        <div class="sidebar-tabs">
          <button
            class="tab-button"
            [class.active]="activeTab === 'sessions'"
            (click)="activeTab = 'sessions'"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
              <path fill-rule="evenodd" d="M4 5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 1h6v8H7V6z" clip-rule="evenodd"/>
            </svg>
            Sessions
          </button>
          <button
            class="tab-button"
            [class.active]="activeTab === 'metrics'"
            (click)="activeTab = 'metrics'"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"/>
            </svg>
            Metrics
          </button>
        </div>

        <!-- Tab Content -->
        <div class="tab-content">
          <!-- Sessions Tab -->
          @if (activeTab === 'sessions') {
            <div class="sessions-tab">
              <!-- Project Filter -->
              @if (hasProjectPath) {
                <div class="project-filter">
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4l2 2h4a2 2 0 012 2v2H8a2 2 0 01-2-2V6zM8 12v4a2 2 0 002 2h4a2 2 0 002-2v-2H8z" clip-rule="evenodd"/>
                  </svg>
                  <span class="project-path">{{ getProjectPathDisplay() }}</span>
                </div>
              }

              <!-- Session Search -->
              <div class="session-search">
                <input
                  type="text"
                  [(ngModel)]="searchQuery"
                  (ngModelChange)="onSearchChange()"
                  class="search-input"
                  placeholder="Search sessions..."
                />
                @if (searchQuery) {
                  <button
                    class="clear-search"
                    (click)="clearSearch()"
                    title="Clear search"
                  >
                    <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                  </button>
                }
              </div>

              <!-- Session List -->
              <div class="sessions-list">
                @if (filteredSessions.length === 0) {
                  <div class="empty-state">
                    <svg class="w-8 h-8 mx-auto mb-2 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z"/>
                      <path fill-rule="evenodd" d="M4 5a2 2 0 012-2h8a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 1h6v8H7V6z" clip-rule="evenodd"/>
                    </svg>
                    <p class="empty-text">{{ searchQuery ? 'No sessions found' : 'No sessions yet' }}</p>
                    @if (!searchQuery) {
                      <button
                        class="empty-action"
                        (click)="createNewSession()"
                      >
                        Create your first session
                      </button>
                    }
                  </div>
                } @else {
                  @for (session of filteredSessions; track session.id) {
                    <app-session-item
                      [session]="session"
                      [isActive]="session.id === currentSessionId"
                      [isStreaming]="isStreaming"
                      (sessionSelect)="onSessionSelect($event)"
                      (sessionDelete)="onSessionDelete($event)"
                    ></app-session-item>
                  }
                }
              </div>
            </div>
          }

          <!-- Metrics Tab -->
          @if (activeTab === 'metrics') {
            <div class="metrics-tab">
              <app-metrics-panel
                [sessionMetrics]="currentSessionMetrics"
                [projectMetrics]="currentProjectMetrics"
                (refreshMetrics)="refreshMetrics()"
              ></app-metrics-panel>
            </div>
          }
        </div>
      </div>

      <!-- Sidebar Footer -->
      <div class="sidebar-footer">
        <!-- Quick Actions -->
        <div class="quick-actions">
          <button
            class="action-button"
            (click)="refreshSessions()"
            [disabled]="isRefreshing"
            title="Refresh sessions"
          >
            <svg class="w-3 h-3" [class]="isRefreshing ? 'animate-spin' : ''" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>
            </svg>
          </button>

          <button
            class="action-button"
            (click)="toggleSettings()"
            [class.active]="showSettings"
            title="Settings"
          >
            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-3.295 2.413a1.532 1.532 0 01-2.118.948 1.532 1.532 0 01-.948 2.118c-1.679.353-3.249 1.923-2.413 3.295a1.532 1.532 0 01-.948 2.286c0 1.378.848 2.58 2.119 2.947a1.532 1.532 0 01-.948 2.118c-.353 1.679.734 3.249 2.413 3.295a1.532 1.532 0 012.118.948 1.532 1.532 0 012.118-.948c1.372.836 2.942-.734 3.295-2.413a1.532 1.532 0 012.118-.948 1.532 1.532 0 01.948-2.118c1.679-.353 3.249-1.923 2.413-3.295a1.532 1.532 0 01.948-2.286c0-1.378-.848-2.58-2.119-2.947a1.532 1.532 0 01.948-2.118c.353-1.679-.734-3.249-2.413-3.295zM12 12.75a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM7.5 10.5a.75.75 0 111.5 0 .75.75 0 01-1.5 0z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>

        <!-- Session Count -->
        <div class="session-count">
          {{ sessions.length }} session{{ sessions.length !== 1 ? 's' : '' }}
        </div>
      </div>
    </div>
  `,
  styles: [`
    .sidebar-container {
      @apply h-full flex flex-col bg-gray-50 border-r border-gray-200 w-80;
    }

    .sidebar-header {
      @apply p-4 border-b border-gray-200 bg-white;
    }

    .header-content {
      @apply flex items-center justify-between mb-2;
    }

    .app-title {
      @apply flex items-center gap-2 text-lg font-semibold text-gray-900;
    }

    .new-session-button {
      @apply flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed;
    }

    .button-text {
      @apply text-sm font-medium;
    }

    .connection-status {
      @apply flex items-center gap-2 text-xs;
    }

    .status-dot {
      @apply w-2 h-2 rounded-full;
    }

    .connection-status.connected .status-dot {
      @apply bg-green-500;
    }

    .connection-status.connecting .status-dot {
      @apply bg-yellow-500 animate-pulse;
    }

    .connection-status.disconnected .status-dot {
      @apply bg-red-500;
    }

    .connection-status.error .status-dot {
      @apply bg-red-500;
    }

    .status-text {
      @apply text-gray-600;
    }

    .sidebar-content {
      @apply flex-1 overflow-hidden flex flex-col;
    }

    .sidebar-tabs {
      @apply flex bg-white border-b border-gray-200;
    }

    .tab-button {
      @apply flex-1 flex items-center justify-center gap-2 px-3 py-3 text-sm font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-50 transition-colors duration-200 border-b-2 border-transparent;
    }

    .tab-button.active {
      @apply text-blue-600 border-blue-600 bg-blue-50;
    }

    .tab-content {
      @apply flex-1 overflow-y-auto bg-gray-50;
    }

    .sessions-tab, .metrics-tab {
      @apply p-4 space-y-4;
    }

    .project-filter {
      @apply flex items-center gap-2 p-2 bg-blue-50 border border-blue-200 rounded-lg text-sm;
    }

    .project-path {
      @apply text-blue-700 font-medium truncate;
    }

    .session-search {
      @apply relative;
    }

    .search-input {
      @apply w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent;
    }

    .search-input::placeholder {
      @apply text-gray-400;
    }

    .search-input::before {
      content: '';
      @apply absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4;
    }

    .clear-search {
      @apply absolute right-3 top-1/2 transform -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 transition-colors duration-200;
    }

    .sessions-list {
      @apply space-y-2;
    }

    .empty-state {
      @apply flex flex-col items-center justify-center py-8 text-center;
    }

    .empty-text {
      @apply text-sm text-gray-500 mb-4;
    }

    .empty-action {
      @apply px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors duration-200;
    }

    .sidebar-footer {
      @apply p-4 border-t border-gray-200 bg-white;
    }

    .quick-actions {
      @apply flex items-center justify-center gap-2 mb-2;
    }

    .action-button {
      @apply p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors duration-200;
    }

    .action-button.active {
      @apply text-blue-600 bg-blue-50;
    }

    .action-button:disabled {
      @apply opacity-50 cursor-not-allowed;
    }

    .session-count {
      @apply text-center text-xs text-gray-500;
    }

    /* Mobile adjustments */
    @media (max-width: 640px) {
      .sidebar-container {
        @apply w-full;
      }

      .button-text {
        @apply hidden;
      }

      .app-title {
        @apply text-base;
      }
    }
  `]
})
export class SidebarComponent implements OnInit, OnDestroy {
  activeTab: 'sessions' | 'metrics' = 'sessions';
  searchQuery: string = '';
  isCreatingSession: boolean = false;
  isRefreshing: boolean = false;
  isStreaming: boolean = false;
  showSettings: boolean = false;

  sessions: Session[] = [];
  filteredSessions: Session[] = [];
  currentSessionId: string | null = null;
  currentSessionMetrics: SessionMetrics = {
    totalTokens: 0,
    sessionCost: 0,
    toolCalls: 0
  };
  currentProjectMetrics: ProjectMetrics = {
    totalCost: 0,
    totalTokens: 0,
    totalSessions: 0
  };

  private subscriptions: Subscription[] = [];

  constructor(
    private sessionService: SessionService,
    private metricsService: MetricsService,
    private chatService: ChatService,
    private configService: ConfigService
  ) {}

  ngOnInit(): void {
    this.setupSubscriptions();
    this.loadSessions();
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach(sub => sub.unsubscribe());
  }

  private setupSubscriptions(): void {
    // Subscribe to session changes
    this.subscriptions.push(
      this.sessionService.activeSessions.subscribe(sessions => {
        this.sessions = sessions;
        this.filteredSessions = this.filterSessions(sessions, this.searchQuery);
      })
    );

    this.subscriptions.push(
      this.sessionService.currentSessionId.subscribe(sessionId => {
        this.currentSessionId = sessionId;
        if (sessionId) {
          this.loadSessionMetrics(sessionId);
        }
      })
    );

    // Subscribe to metrics changes
    this.subscriptions.push(
      this.metricsService.sessionMetrics.subscribe(metrics => {
        this.currentSessionMetrics = metrics;
      })
    );

    this.subscriptions.push(
      this.metricsService.projectMetrics.subscribe(metrics => {
        this.currentProjectMetrics = metrics;
      })
    );

    // Subscribe to config changes
    this.subscriptions.push(
      this.configService.config.subscribe(config => {
        this.showSettings = config.showSettings;
      })
    );
  }

  private loadSessions(): void {
    this.isRefreshing = true;
    const projectPath = this.sessionService.getProjectPath();
    this.chatService.listSessions(projectPath || undefined).subscribe({
      next: () => {
        this.isRefreshing = false;
      },
      error: (error) => {
        console.error('Failed to load sessions:', error);
        this.isRefreshing = false;
      }
    });
  }

  private loadSessionMetrics(sessionId: string): void {
    const sessionState = this.metricsService.getSessionState(sessionId);
    if (sessionState) {
      this.currentSessionMetrics = {
        totalTokens: sessionState.totalTokens,
        sessionCost: sessionState.totalCost,
        toolCalls: 0 // Will be updated from streaming events
      };
    }
  }

  createNewSession(): void {
    if (this.isCreatingSession) return;

    this.isCreatingSession = true;
    this.sessionService.createSession().then(sessionId => {
      this.isCreatingSession = false;
    }).catch(error => {
      console.error('Failed to create session:', error);
      this.isCreatingSession = false;
    });
  }

  refreshSessions(): void {
    this.loadSessions();
  }

  refreshMetrics(): void {
    // MetricsService handles its own refresh logic
  }

  onSearchChange(): void {
    this.filteredSessions = this.filterSessions(this.sessions, this.searchQuery);
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.filteredSessions = this.sessions;
  }

  private filterSessions(sessions: Session[], query: string): Session[] {
    if (!query.trim()) {
      return sessions;
    }

    const lowerQuery = query.toLowerCase();
    return sessions.filter(session =>
      session.title.toLowerCase().includes(lowerQuery) ||
      session.id.toLowerCase().includes(lowerQuery)
    );
  }

  onSessionSelect(session: Session): void {
    this.sessionService.selectSession(session.id);
  }

  onSessionDelete(session: Session): void {
    this.sessionService.hideSession(session.id);
  }

  toggleSettings(): void {
    this.configService.toggleSettings();
  }

  get hasProjectPath(): boolean {
    return !!this.sessionService.getProjectPath();
  }

  getProjectPathDisplay(): string {
    const path = this.sessionService.getProjectPath();
    if (!path) return '';
    // Show just the last part of the path
    return path.split('/').pop() || path;
  }

  getConnectionStatusClass(): string {
    const config = this.configService.getConfig();
    return config.connectionState;
  }

  getConnectionStatusText(): string {
    const config = this.configService.getConfig();
    switch (config.connectionState) {
      case 'connected':
        return 'Godot Connected';
      case 'connecting':
        return 'Connecting...';
      case 'disconnected':
        return 'Godot Disconnected';
      case 'error':
        return 'Connection Error';
      default:
        return 'Unknown Status';
    }
  }
}