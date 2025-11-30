import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

export interface Session {
  id: string;
  title: string;
  date: Date;
  active: boolean;
  metrics?: {
    session_cost: number;
    session_tokens: number;
  };
  project_path?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  tokens?: number;
  promptTokens?: number;
  completionTokens?: number;
  cost?: number;
  modelName?: string;
  generationTimeMs?: number;
  isStreaming?: boolean;
  toolCalls?: any[];
  plan?: any;
  events?: any[];
  workflowMetrics?: any;
}

@Injectable({
  providedIn: 'root'
})
export class SessionService {
  public currentSessionId: BehaviorSubject<string | null> = new BehaviorSubject<string | null>(null);
  public activeSessions: BehaviorSubject<Session[]> = new BehaviorSubject<Session[]>([]);
  public messages: BehaviorSubject<Map<string, Message[]>> = new BehaviorSubject<Map<string, Message[]>>(new Map());

  private currentProjectPath: string | null = null;
  private sessionMessages: Map<string, Message[]> = new Map();

  constructor() { }

  /**
   * Initialize the session service
   */
  async initialize(): Promise<void> {
    // Restore last active session from localStorage if available
    const lastSessionId = localStorage.getItem('godoty_last_session_id');
    const lastProjectPath = localStorage.getItem('godoty_last_project_path');

    if (lastProjectPath) {
      this.setProjectPath(lastProjectPath);
    }

    if (lastSessionId) {
      await this.selectSession(lastSessionId);
    }
  }

  /**
   * Set the current project path for session filtering
   */
  setProjectPath(path: string): void {
    this.currentProjectPath = path;
    localStorage.setItem('godoty_last_project_path', path);
  }

  /**
   * Get the current project path
   */
  getProjectPath(): string | null {
    return this.currentProjectPath;
  }

  /**
   * Create a new session
   */
  async createSession(title?: string): Promise<string> {
    const sessionId = `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const sessionTitle = title || 'New Session';

    const newSession: Session = {
      id: sessionId,
      title: sessionTitle,
      date: new Date(),
      active: true,
      project_path: this.currentProjectPath || undefined
    };

    // Add to sessions list
    const currentSessions = this.activeSessions.value;
    this.activeSessions.next([newSession, ...currentSessions]);

    // Initialize messages map for this session
    this.sessionMessages.set(sessionId, []);
    this.messages.next(new Map(this.sessionMessages));

    // Select the new session
    await this.selectSession(sessionId);

    return sessionId;
  }

  /**
   * Select an existing session
   */
  async selectSession(sessionId: string): Promise<void> {
    this.currentSessionId.next(sessionId);
    localStorage.setItem('godoty_last_session_id', sessionId);

    // Update active states
    const sessions = this.activeSessions.value.map(session => ({
      ...session,
      active: session.id === sessionId
    }));
    this.activeSessions.next(sessions);

    // Load session history if not already loaded
    if (!this.sessionMessages.has(sessionId)) {
      await this.loadSessionHistory(sessionId);
    }
  }

  /**
   * Hide (soft delete) a session
   */
  async hideSession(sessionId: string): Promise<void> {
    // Remove from sessions list
    const currentSessions = this.activeSessions.value;
    const filteredSessions = currentSessions.filter(session => session.id !== sessionId);
    this.activeSessions.next(filteredSessions);

    // Clear messages for this session
    this.sessionMessages.delete(sessionId);
    this.messages.next(new Map(this.sessionMessages));

    // If this was the current session, clear current session
    if (this.currentSessionId.value === sessionId) {
      this.currentSessionId.next(null);
      localStorage.removeItem('godoty_last_session_id');
    }
  }

  /**
   * Load session history (placeholder for backend integration)
   */
  async loadSessionHistory(sessionId: string): Promise<Message[]> {
    // This will be integrated with the backend API
    // For now, return empty array
    const history: Message[] = [];
    this.sessionMessages.set(sessionId, history);
    this.messages.next(new Map(this.sessionMessages));
    return history;
  }

  /**
   * Add a message to the current session
   */
  addMessage(sessionId: string, message: Message): void {
    const sessionMessages = this.sessionMessages.get(sessionId) || [];
    const updatedMessages = [...sessionMessages, message];
    this.sessionMessages.set(sessionId, updatedMessages);
    this.messages.next(new Map(this.sessionMessages));
  }

  /**
   * Update a message in the current session
   */
  updateMessage(sessionId: string, messageId: string, updates: Partial<Message>): void {
    const sessionMessages = this.sessionMessages.get(sessionId) || [];
    const messageIndex = sessionMessages.findIndex(msg => msg.id === messageId);

    if (messageIndex !== -1) {
      sessionMessages[messageIndex] = { ...sessionMessages[messageIndex], ...updates };
      this.sessionMessages.set(sessionId, sessionMessages);
      this.messages.next(new Map(this.sessionMessages));
    }
  }

  /**
   * Get messages for a specific session
   */
  getMessages(sessionId: string): Message[] {
    return this.sessionMessages.get(sessionId) || [];
  }

  /**
   * Get a specific message by ID
   */
  getMessage(sessionId: string, messageId: string): Message | undefined {
    const sessionMessages = this.sessionMessages.get(sessionId) || [];
    return sessionMessages.find(msg => msg.id === messageId);
  }

  /**
   * Get the current session ID
   */
  getCurrentSessionId(): string | null {
    return this.currentSessionId.value;
  }

  /**
   * Get the current session's messages
   */
  getCurrentSessionMessages(): Message[] {
    const currentSessionId = this.currentSessionId.value;
    if (!currentSessionId) return [];
    return this.getMessages(currentSessionId);
  }

  /**
   * Update sessions list (called from ChatService after API calls)
   */
  updateSessionsList(sessions: Session[]): void {
    // Filter by project path if set
    let filteredSessions = sessions;
    if (this.currentProjectPath) {
      filteredSessions = sessions.filter(session =>
        session.project_path === this.currentProjectPath
      );
    }

    this.activeSessions.next(filteredSessions);
  }

  /**
   * Update session metadata (e.g., after getting session details)
   */
  updateSessionMetadata(sessionId: string, metadata: Partial<Session>): void {
    const currentSessions = this.activeSessions.value;
    const updatedSessions = currentSessions.map(session =>
      session.id === sessionId ? { ...session, ...metadata } : session
    );
    this.activeSessions.next(updatedSessions);
  }

  /**
   * Clear all sessions (for testing or logout)
   */
  clearAllSessions(): void {
    this.activeSessions.next([]);
    this.sessionMessages.clear();
    this.messages.next(new Map(this.sessionMessages));
    this.currentSessionId.next(null);
    localStorage.removeItem('godoty_last_session_id');
    localStorage.removeItem('godoty_last_project_path');
  }
}