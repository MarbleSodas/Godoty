import { Injectable, NgZone } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { listen, UnlistenFn } from '@tauri-apps/api/event';

export interface LlmStreamDelta {
  sessionId?: string | null;
  delta: string;
  model?: string;
}

export interface LlmStreamCompleted {
  sessionId?: string | null;
  text: string;
  model?: string;
}

@Injectable({ providedIn: 'root' })
export class LlmStreamService {
  private delta$ = new Subject<LlmStreamDelta>();
  private done$ = new Subject<LlmStreamCompleted>();
  private unlisten: UnlistenFn | null = null;

  constructor(private zone: NgZone) {
    this.init();
  }

  private async init() {
    try {
      // Backend emits on 'tool-call-delta' with payload.event = 'llm_stream' | 'llm_stream_completed'
      this.unlisten = await listen('tool-call-delta', (event) => {
        const p: any = event.payload as any;
        const evt = p?.event as string | undefined;
        if (evt === 'llm_stream') {
          const payload: LlmStreamDelta = { sessionId: p?.sessionId ?? p?.session_id, delta: p?.delta || '', model: p?.model };
          this.zone.run(() => this.delta$.next(payload));
        } else if (evt === 'llm_stream_completed') {
          const payload: LlmStreamCompleted = { sessionId: p?.sessionId ?? p?.session_id, text: p?.text || '', model: p?.model };
          this.zone.run(() => this.done$.next(payload));
        }
      });
    } catch (e) {
      console.warn('LlmStreamService: failed to listen to tool-call-delta events', e);
    }
  }

  onDelta(): Observable<LlmStreamDelta> { return this.delta$.asObservable(); }
  onCompleted(): Observable<LlmStreamCompleted> { return this.done$.asObservable(); }
}

