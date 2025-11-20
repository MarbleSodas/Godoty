import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map, tap } from 'rxjs';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  tokens?: number;
  cost?: number;
  isStreaming?: boolean;
}

export interface Session {
  id: string;
  title: string;
  date: Date;
  active: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private apiUrl = 'http://127.0.0.1:8000/api/agent';

  constructor(private http: HttpClient) { }

  // Session Management
  createSession(sessionId: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/sessions`, { session_id: sessionId });
  }

  listSessions(): Observable<Session[]> {
    return this.http.get<any>(`${this.apiUrl}/sessions`).pipe(
      map(response => {
        if (response.status === 'success' && response.sessions) {
          // Map backend session format to frontend interface if needed
          // For now assuming backend returns compatible list or we adapt here
          return Object.entries(response.sessions).map(([id, data]: [string, any]) => ({
            id: id,
            title: data.metadata?.title || `Session ${id}`, // Fallback title
            date: new Date(data.created_at || Date.now()),
            active: false
          }));
        }
        return [];
      })
    );
  }

  getSession(sessionId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/sessions/${sessionId}`);
  }

  deleteSession(sessionId: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/sessions/${sessionId}`);
  }

  // Chat Interaction
  sendMessage(sessionId: string, message: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/sessions/${sessionId}/chat`, { message });
  }

  async *sendMessageStream(sessionId: string, message: string): AsyncGenerator<any> {
    const response = await fetch(`${this.apiUrl}/sessions/${sessionId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error('Response body is null');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            try {
              yield JSON.parse(data);
            } catch (e) {
              console.error('Error parsing SSE data:', e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  // Plan Generation (Direct Agent)
  createPlan(prompt: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/plan`, { prompt });
  }
}
