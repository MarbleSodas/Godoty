import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink } from '@angular/router';
import { invoke } from '@tauri-apps/api/core';
import { Command, ConnectionStatus, ChatSession, ChatMessage, MessageStatus } from './models/command.model';
import { ProcessLogService } from './services/process-log.service';
import { StatusPanelComponent } from './components/status-panel/status-panel.component';
import { SettingsPanelComponent } from './components/settings-panel/settings-panel.component';
import { ChatViewComponent } from './components/chat-view/chat-view.component';
import { SessionManagerComponent } from './components/session-manager/session-manager.component';
import { ProcessLogsComponent } from './components/process-logs/process-logs.component';
import { MetricsPanelComponent } from './components/metrics-panel/metrics-panel.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    StatusPanelComponent,
    SettingsPanelComponent,
    ChatViewComponent,
    SessionManagerComponent,
    ProcessLogsComponent,
    MetricsPanelComponent
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  constructor(private logs: ProcessLogService) {}
  commands: Command[] = [];
  connectionStatus: ConnectionStatus = 'disconnected';
  apiKey: string = '';
  projectPath: string = '';

  // Chat session management
  chatSessions: ChatSession[] = [];
  activeSession: ChatSession | null = null;

  // Processing state
  isProcessing: boolean = false;
  processingStatus: MessageStatus | null = null;

  ngOnInit(): void {
    this.loadApiKey();
    this.loadProjectPath();
    this.connectToGodot();
    this.loadChatSessions();
  }

  async loadApiKey(): Promise<void> {
    try {
      this.apiKey = await invoke<string>('get_api_key');
    } catch (error) {
      console.error('Failed to load API key:', error);
    }
  }

  async loadProjectPath(): Promise<void> {
    try {
      this.projectPath = await invoke<string>('get_godot_project_path');
    } catch (error) {
      console.error('Failed to load project path:', error);
    }
  }

  async connectToGodot(): Promise<void> {
    this.connectionStatus = 'connecting';
    this.logs.add({ level: 'info', category: 'agent_activity', message: 'Connecting to Godot...', agent: 'Bridge', status: 'processing' });
    try {
      await invoke('connect_to_godot');
      this.connectionStatus = 'connected';
      this.logs.add({ level: 'info', category: 'agent_activity', message: 'Connected to Godot', agent: 'Bridge', status: 'completed' });
    } catch (error) {
      console.error('Failed to connect to Godot:', error);
      this.connectionStatus = 'disconnected';
      this.logs.add({ level: 'error', category: 'agent_activity', message: 'Failed to connect to Godot', agent: 'Bridge', status: 'error', data: { error: String(error) } });
    }
  }

  // Temporary client-only session ID used when no active session exists yet
  private _tempSessionId: string | null = null;

  async handleCommandSubmit(input: string): Promise<void> {
    const command: Command = {
      id: Date.now().toString(),
      input,
      timestamp: new Date(),
      status: 'pending'
    };

    this.commands = [command, ...this.commands];

    // Set processing state immediately so the UI shows activity
    this.isProcessing = true;
    this.processingStatus = 'sending';

    // Create an optimistic user message for instant UI feedback
    const nowSec = Math.floor(Date.now() / 1000);
    const optimisticMessage: ChatMessage = {
      id: `tmp-${nowSec}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: input,
      timestamp: nowSec,
      status: 'sending',
      isStreaming: false
    };

    // Apply optimistic update to active session and session list
    let usedTempSession = false;
    if (this.activeSession) {
      const updatedActive: ChatSession = {
        ...this.activeSession,
        messages: [...this.activeSession.messages, optimisticMessage],
        updated_at: nowSec
      };
      this.activeSession = updatedActive; // triggers change detection
      // Update session in list immutably so Session Manager reflects instantly
      this.chatSessions = this.chatSessions.map(s =>
        s.id === updatedActive.id ? { ...s, messages: updatedActive.messages, updated_at: nowSec } : s
      );
    } else {
      // No active session yet: create a temporary client-only session so UI updates instantly
      usedTempSession = true;
      this._tempSessionId = `temp-${nowSec}-${Math.random().toString(36).slice(2, 6)}`;
      const tempSession: ChatSession = {
        id: this._tempSessionId,
        title: 'New Session',
        messages: [optimisticMessage],
        created_at: nowSec,
        updated_at: nowSec,
        project_path: this.projectPath,
        metadata: {
          total_commands: 0,
          successful_commands: 0,
          failed_commands: 0,
          total_tokens_used: 0
        }
      };
      this.activeSession = tempSession;
      this.chatSessions = [tempSession, ...this.chatSessions];
    }

    // Stream backend activity logs as inline system chat messages during processing
    const startMs = Date.now();
    const logsSub = this.logs.onEntry().subscribe((entry) => {
      if (!this.activeSession) return;
      if (entry.timestamp && entry.timestamp < startMs) return; // ignore old entries
      if (entry.sessionId && this.activeSession.id !== entry.sessionId) return; // different session

      const statusMap: Record<string, MessageStatus> = {
        idle: 'thinking',
        processing: 'executing',
        waiting: 'thinking',
        completed: 'complete',
        error: 'error'
      } as any;

      const parts: string[] = [];
      if (entry.agent) parts.push(entry.agent);
      if (entry.task) parts.push(`— ${entry.task}`);
      const bracket = parts.length ? ` [${parts.join(' ')}]` : '';
      const text = `${(entry.level || 'info').toUpperCase()}${bracket}: ${entry.message}`;

      const msg: ChatMessage = {
        id: `log-${entry.id}`,
        role: 'system',
        content: text,
        timestamp: Math.floor(((entry.timestamp as number) || Date.now()) / 1000),
        status: statusMap[(entry.status as string) || 'processing'] || 'thinking',
        isStreaming: false
      };

      const updated: ChatSession = {
        ...this.activeSession,
        messages: [...this.activeSession.messages, msg],
        updated_at: Math.floor(Date.now() / 1000)
      };
      this.activeSession = updated;
      this.chatSessions = this.chatSessions.map(s => s.id === updated.id ? { ...s, messages: updated.messages, updated_at: updated.updated_at } : s);
    });

    try {
      // Update status to thinking before backend call to keep UI lively
      this.processingStatus = 'thinking';
      // Emit client-side log to kick off inline activity stream
      this.logs.add({ level: 'info', category: 'agent_activity', message: 'AI processing started', agent: 'Assistant', status: 'processing', sessionId: this.activeSession?.id || this._tempSessionId || undefined });

      const response = await invoke<string>('process_command_agentic', { input });

      // Update status to complete
      this.processingStatus = 'complete';
      this.logs.add({ level: 'info', category: 'agent_activity', message: 'AI processing complete', agent: 'Assistant', status: 'completed', sessionId: this.activeSession?.id || undefined });

      this.commands = this.commands.map(cmd =>
        cmd.id === command.id ? { ...cmd, status: 'success', response } : cmd
      );

      // Reconcile with backend session: fetch the authoritative active session
      await this.loadActiveSession();

      // Reflect the fetched active session in the sessions list
      if (this.activeSession) {
        if (usedTempSession && this._tempSessionId) {
          // Replace the temp session entry with the real one
          const real = this.activeSession;
          let replaced = false;
          this.chatSessions = this.chatSessions.map(s => {
            if (s.id === this._tempSessionId) {
              replaced = true;
              return real;
            }
            return s.id === real.id ? real : s;
          });
          if (!replaced) {
            // If temp wasn't found (edge case), ensure the real session is present at top
            const withoutReal = this.chatSessions.filter(s => s.id !== real.id);
            this.chatSessions = [real, ...withoutReal];
          }
          this._tempSessionId = null;
        } else {
          // Update the matching session entry with the freshly loaded active session
          const real = this.activeSession;
          this.chatSessions = this.chatSessions.map(s => (s.id === real.id ? real : s));
        }
      }
    } catch (error) {
      this.processingStatus = 'error';
      this.logs.add({ level: 'error', category: 'agent_activity', message: 'AI processing failed', agent: 'Assistant', status: 'error', sessionId: this.activeSession?.id || this._tempSessionId || undefined, data: { error: String(error) } });

      this.commands = this.commands.map(cmd =>
        cmd.id === command.id ? { ...cmd, status: 'error', response: String(error) } : cmd
      );

      // Even on error, backend has appended the user message; reconcile state
      await this.loadActiveSession().catch(() => {});

      if (this.activeSession) {
        if (usedTempSession && this._tempSessionId) {
          const real = this.activeSession;
          this.chatSessions = this.chatSessions.map(s => (s.id === this._tempSessionId ? real : s));
          this._tempSessionId = null;
        } else {
          const real = this.activeSession;
          this.chatSessions = this.chatSessions.map(s => (s.id === real.id ? real : s));
        }
      }
    } finally {
      // Stop streaming logs for this request
      try { logsSub.unsubscribe(); } catch {}
      // Clear processing state immediately (no artificial delay)
      this.isProcessing = false;
      this.processingStatus = null;
    }
  }

  async handleSaveApiKey(key: string): Promise<void> {
    try {
      await invoke('save_api_key', { key });
      this.apiKey = key;
    } catch (error) {
      console.error('Failed to save API key:', error);
    }
  }

  async handleSaveProjectPath(path: string): Promise<void> {
    try {
      await invoke('set_godot_project_path', { path });
      this.projectPath = path;
    } catch (error) {
      console.error('Failed to save project path:', error);
    }
  }

  // Chat session management methods
  async loadChatSessions(): Promise<void> {
    try {
      const sessions = await invoke<ChatSession[]>('get_all_sessions');
      this.chatSessions = sessions;
      await this.loadActiveSession();
    } catch (error) {
      console.error('Failed to load chat sessions:', error);
      this.chatSessions = [];
    }
  }

  async loadActiveSession(): Promise<void> {
    try {
      this.activeSession = await invoke<ChatSession>('get_active_session');
    } catch (error) {
      // No active session is fine
      this.activeSession = null;
    }
  }

  async handleCreateSession(title: string): Promise<void> {
    try {
      await invoke('create_chat_session', { title });
      await this.loadChatSessions();
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  }

  async handleSelectSession(sessionId: string): Promise<void> {
    try {
      await invoke('set_active_session', { sessionId });
      await this.loadActiveSession();
    } catch (error) {
      console.error('Failed to select session:', error);
    }
  }

  async handleDeleteSession(sessionId: string): Promise<void> {
    try {
      await invoke('delete_session', { sessionId });
      await this.loadChatSessions();
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  }

  async handleClearAllSessions(): Promise<void> {
    try {
      await invoke('clear_all_sessions');
      await this.loadChatSessions();
    } catch (error) {
      console.error('Failed to clear sessions:', error);
    }
  }

  async handleQuickCreateSession(): Promise<void> {
    const timestamp = new Date().toLocaleString();
    await this.handleCreateSession(`Chat ${timestamp}`);
  }
}

