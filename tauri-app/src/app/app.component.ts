import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink } from '@angular/router';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { Command, ConnectionStatus, ChatSession, ChatMessage, MessageStatus } from './models/command.model';
import { IndexingStatus, IndexingStatusResponse, IndexingStatusEvent } from './models/indexing-status.model';
import { ProcessLogService } from './services/process-log.service';
import { ProcessLogEntry } from './models/process-log.model';

import { StatusPanelComponent } from './components/status-panel/status-panel.component';
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
  indexingStatus: IndexingStatus | null = null;

  // Chat session management
  chatSessions: ChatSession[] = [];
  activeSession: ChatSession | null = null;

  // Processing state
  isProcessing: boolean = false;
  // Inline chat logging helpers
  private logChatUpdate(
    actionType: string,
    details: any,
    status: 'idle' | 'processing' | 'waiting' | 'completed' | 'error' = 'processing',
    message?: string
  ): void {
    this.logs.add({
      level: 'info',
      category: 'message_update',
      message: message || actionType,
      actionType,
      status,
      sessionId: this.activeSession?.id || this._tempSessionId || undefined,
      data: details,
      details,
    } as any);
  }

  // Merge ephemeral inline system log messages into the latest server session
  private mergeInlineSystemLogs(session: ChatSession): ChatSession {
    if (!this.activeSession) return session;
    const targetId = session.id;
    const existingSystemLogs = (this.activeSession.messages || []).filter(
      (m) => m.role === 'system' && (m.id?.startsWith?.('log-') ?? false) && m.sessionId === targetId
    );
    if (!existingSystemLogs.length) return session;

    const incomingIds = new Set((session.messages || []).map((m) => m.id));
    const toAdd = existingSystemLogs.filter((m) => !incomingIds.has(m.id));
    if (!toAdd.length) return session;

    const merged: ChatSession = {
      ...session,
      messages: [...session.messages, ...toAdd].sort((a, b) => a.timestamp - b.timestamp),
    };
    return merged;
  }

  processingStatus: MessageStatus | null = null;

  ngOnInit(): void {
    this.loadApiKey();
    this.loadProjectPath();
    this.loadIndexingStatus();
    this.listenToIndexingStatusChanges();
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

  async loadIndexingStatus(): Promise<void> {
    try {
      const response = await invoke<IndexingStatusResponse>('get_indexing_status');
      this.indexingStatus = response.status;
      if (response.projectPath) {
        this.projectPath = response.projectPath;
      }
    } catch (error) {
      console.error('Failed to load indexing status:', error);
    }
  }

  async listenToIndexingStatusChanges(): Promise<void> {
    try {
      await listen<IndexingStatusEvent>('indexing-status-changed', (event) => {
        console.log('Indexing status changed:', event.payload);
        this.indexingStatus = event.payload.status;
        if (event.payload.projectPath) {
          this.projectPath = event.payload.projectPath;
        }
      });
    } catch (error) {
      console.error('Failed to listen to indexing status changes:', error);
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

    this.logChatUpdate('Status Change', { status: 'sending' }, 'processing', 'Message status updated');

    // Create an optimistic user message for instant UI feedback
    const nowSec = Math.floor(Date.now() / 1000);
    const optimisticMessage: ChatMessage = {
      id: `tmp-${nowSec}-${Math.random().toString(36).slice(2, 8)}`,
      sessionId: this.activeSession?.id || this._tempSessionId || undefined,
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
    this.logChatUpdate('Message Created', { id: optimisticMessage.id, role: 'user', length: input.length }, 'processing');

      this.chatSessions = [tempSession, ...this.chatSessions];
    }

    // Stream backend activity logs as inline system chat messages during processing
    const startMs = Date.now();
    const logsSub = this.logs.onEntry().subscribe((entry) => {
      if (entry.timestamp && entry.timestamp < startMs) return; // ignore old entries

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
      const actionStr = (entry as any).actionType ? ` (${(entry as any).actionType})` : '';
      const details = (entry as any).details || (entry as any).data;
      const knownKeys = ['path','file','function','url','status','status_code','tool','command','args','durationMs','bytes','line_count'];
      const detailParts: string[] = [];
      if (details && typeof details === 'object') {
        for (const k of knownKeys) {
          if (k in (details as any)) {
            const v = (details as any)[k];
            const sval = typeof v === 'string' ? v : JSON.stringify(v);
            detailParts.push(`${k}=${sval}`);
          }
        }
      }
      const extra = detailParts.length ? ` — ${detailParts.join(' ')}` : '';
      const text = `${(entry.level || 'info').toUpperCase()}${bracket}${actionStr}: ${entry.message}${extra}`;

      // If first real-time log references a real session while we're on a temp session, pivot immediately
      if (this.activeSession && this._tempSessionId && entry.sessionId && this.activeSession.id === this._tempSessionId && entry.sessionId !== this._tempSessionId) {
        const realId = entry.sessionId;
        const migrated: ChatSession = {
          ...this.activeSession,
          id: realId,
          messages: this.activeSession.messages.map(m => (!m.sessionId || m.sessionId === this._tempSessionId ? { ...m, sessionId: realId } : m))
        };
        this.activeSession = migrated;
        this.chatSessions = this.chatSessions.map(s => s.id === this._tempSessionId ? migrated : (s.id === realId ? migrated : s));
        this._tempSessionId = null;
      }

      // If the log belongs to another session (not temp pivot), persist it to backend but don't render in current view
      if (this.activeSession && entry.sessionId && this.activeSession.id !== entry.sessionId) {
        const persistTs = Math.floor(((entry.timestamp as number) || Date.now()) / 1000);
        const persistId = `log-${entry.id}`;
        void invoke('append_system_message', { sessionId: entry.sessionId, id: persistId, content: text, timestamp: persistTs }).catch(() => {});
        return;
      }

      // Determine the sessionId for this message (prefer the active session after any pivot)
      const sid = this.activeSession?.id || entry.sessionId || undefined;

      const msgStatus: MessageStatus = (entry.category === 'tool_call' && entry.agent === 'WebSearch' && entry.status === 'started')
        ? 'searching_web'
        : (statusMap[(entry.status as string) || 'processing'] || 'thinking');

      const msg: ChatMessage = {
        id: `log-${entry.id}`,
        sessionId: sid,
        role: 'system',
        content: text,
        timestamp: Math.floor(((entry.timestamp as number) || Date.now()) / 1000),
        status: msgStatus,
        isStreaming: false
      };

      // Avoid duplicate UI entries
      if (this.activeSession && this.activeSession.messages.some(m => m.id === msg.id)) {
        return;
      }

      if (!this.activeSession) return;

      const updated: ChatSession = {
        ...this.activeSession,
        messages: [...this.activeSession.messages, msg],
        updated_at: Math.floor(Date.now() / 1000)
      };
      this.activeSession = updated;
      this.chatSessions = this.chatSessions.map(s => s.id === updated.id ? { ...s, messages: updated.messages, updated_at: updated.updated_at } : s);

      // Persist the system message to backend for durability across reloads
      void invoke('append_system_message', { sessionId: sid, id: msg.id, content: msg.content, timestamp: msg.timestamp }).catch(() => {});
    });

    try {
      // Update status to thinking before backend call to keep UI lively
      this.processingStatus = 'thinking';
      this.logChatUpdate('Status Change', { status: 'thinking' }, 'processing', 'Message status updated');

      // Emit client-side log to kick off inline activity stream
      this.logs.add({ level: 'info', category: 'agent_activity', message: 'AI processing started', agent: 'Assistant', status: 'processing', sessionId: this.activeSession?.id || this._tempSessionId || undefined });

      const response = await invoke<string>('process_command_agentic', { input });

      this.logChatUpdate('Status Change', { status: 'complete' }, 'completed', 'Message status updated');

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
      this.logChatUpdate('Status Change', { status: 'error' }, 'error', 'Message status updated');


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
      this.logChatUpdate('Status Change', { status: 'idle' }, 'idle', 'Message status updated');

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
      this.logChatUpdate('Session List Updated', { count: sessions.length }, 'completed', 'Chat sessions updated');

      await this.loadActiveSession();
    } catch (error) {
      console.error('Failed to load chat sessions:', error);
      this.chatSessions = [];
    }
  }

  async loadActiveSession(): Promise<void> {
    try {
      const session = await invoke<ChatSession>('get_active_session');
      if (session) {
        const merged = this.mergeInlineSystemLogs(session);
        this.activeSession = merged;
      } else {
        this.activeSession = null;
      }
    } catch (error) {
      // No active session is fine; suppress logging here

      // No active session is fine
      this.activeSession = null;
    }
  }

  async handleCreateSession(title: string): Promise<void> {
    try {
      await invoke('create_chat_session', { title });
      this.logChatUpdate('Session Created', { title }, 'completed', 'Chat session created');

      await this.loadChatSessions();
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  }

  async handleSelectSession(sessionId: string): Promise<void> {
    try {
      await invoke('set_active_session', { sessionId });
      this.logChatUpdate('Session Selected', { sessionId }, 'completed', 'Active session changed');

      await this.loadActiveSession();
    } catch (error) {
      console.error('Failed to select session:', error);
    }
  }

  async handleDeleteSession(sessionId: string): Promise<void> {
    try {
      await invoke('delete_session', { sessionId });
      this.logChatUpdate('Session Deleted', { sessionId }, 'completed', 'Chat session deleted');

      await this.loadChatSessions();
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  }

  async handleClearAllSessions(): Promise<void> {
      this.logChatUpdate('All Sessions Cleared', {}, 'completed', 'All chat sessions cleared');

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

