import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { invoke } from '@tauri-apps/api/core';
import { Command, ConnectionStatus, ChatSession, MessageStatus } from './models/command.model';
import { CommandInputComponent } from './components/command-input/command-input.component';
import { StatusPanelComponent } from './components/status-panel/status-panel.component';
import { SettingsPanelComponent } from './components/settings-panel/settings-panel.component';
import { ChatViewComponent } from './components/chat-view/chat-view.component';
import { SessionManagerComponent } from './components/session-manager/session-manager.component';
import { ChatSelectorComponent } from './components/chat-selector/chat-selector.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    CommandInputComponent,
    StatusPanelComponent,
    SettingsPanelComponent,
    ChatViewComponent,
    SessionManagerComponent,
    ChatSelectorComponent
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
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
    try {
      await invoke('connect_to_godot');
      this.connectionStatus = 'connected';
    } catch (error) {
      console.error('Failed to connect to Godot:', error);
      this.connectionStatus = 'disconnected';
    }
  }

  async handleCommandSubmit(input: string): Promise<void> {
    const command: Command = {
      id: Date.now().toString(),
      input,
      timestamp: new Date(),
      status: 'pending'
    };

    this.commands = [command, ...this.commands];

    // Set processing state
    this.isProcessing = true;
    this.processingStatus = 'sending';

    try {
      // Update status to thinking
      this.processingStatus = 'thinking';

      const response = await invoke<string>('process_command', { input });

      // Update status to complete
      this.processingStatus = 'complete';

      this.commands = this.commands.map(cmd =>
        cmd.id === command.id
          ? { ...cmd, status: 'success', response }
          : cmd
      );

      // Reload active session to show new messages
      await this.loadActiveSession();
    } catch (error) {
      this.processingStatus = 'error';

      this.commands = this.commands.map(cmd =>
        cmd.id === command.id
          ? { ...cmd, status: 'error', response: String(error) }
          : cmd
      );

      // Reload active session even on error to show the error message
      await this.loadActiveSession();
    } finally {
      // Clear processing state after a short delay
      setTimeout(() => {
        this.isProcessing = false;
        this.processingStatus = null;
      }, 500);
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

