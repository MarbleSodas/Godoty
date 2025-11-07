import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Subject, Observable } from 'rxjs';
import { listen, UnlistenFn } from '@tauri-apps/api/event';
import { ProcessLogEntry, LogLevel, LogCategory } from '../models/process-log.model';

@Injectable({ providedIn: 'root' })
export class ProcessLogService {
  private readonly logs$ = new BehaviorSubject<ProcessLogEntry[]>([]);
  private readonly entry$ = new Subject<ProcessLogEntry>();
  private unlisten: UnlistenFn | null = null;

  constructor(private zone: NgZone) {
    // Subscribe to backend process-log events
    this.initEventListener();
  }

  private async initEventListener(): Promise<void> {
    try {
      this.unlisten = await listen('process-log', (event) => {
        const payload: any = event.payload as any;
        const entry: ProcessLogEntry = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          timestamp: typeof payload?.timestamp === 'number' ? payload.timestamp : Date.now(),
          level: (payload?.level as LogLevel) || 'info',
          category: (payload?.category as LogCategory) || 'action',
          message: payload?.message || 'Event',
          agent: payload?.agent,
          task: payload?.task,
          actionType: (payload as any)?.actionType || (payload as any)?.data?.actionType,
          status: payload?.status,
          sessionId: payload?.sessionId,
          details: (payload as any)?.details || (payload as any)?.data,
          data: payload?.data,
        };
        this.zone.run(() => this.append(entry));
      });
    } catch (e) {
      // If event system is unavailable, silently ignore
      console.warn('ProcessLogService: failed to listen to process-log events', e);
    }
  }

  getLogs() {
    return this.logs$.asObservable();
  }

  // Stream of individual log entries as they arrive (real-time)
  onEntry(): Observable<ProcessLogEntry> {
    return this.entry$.asObservable();
  }

  getLogsForSession(sessionId?: string | null) {
    return this.logs$.asObservable();
  }

  clear() {
    this.logs$.next([]);
  }

  // Client-side helper to add logs from UI actions
  add(entry: Omit<ProcessLogEntry, 'id' | 'timestamp'> & { timestamp?: number }) {
    const full: ProcessLogEntry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: entry.timestamp ?? Date.now(),
      ...entry,
    } as ProcessLogEntry;
    this.append(full);
  }

  private append(entry: ProcessLogEntry) {
    const current = this.logs$.value;
    // Keep only recent N entries to avoid unbounded growth
    const MAX = 500;
    const next = [...current, entry].slice(-MAX);
    this.logs$.next(next);
    // Emit individual entry for real-time consumers (e.g., chat stream)
    this.entry$.next(entry);
  }
}

