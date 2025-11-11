import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { invoke } from '@tauri-apps/api/core';
import { listen, UnlistenFn } from '@tauri-apps/api/event';

interface LiteLLMStatus {
  running: boolean;
  port?: number | null;
  last_error?: string | null;
}

@Component({
  selector: 'app-sidecar-status',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sidecar-status.component.html',
  styleUrls: ['./sidecar-status.component.css']
})
export class SidecarStatusComponent implements OnInit, OnDestroy {
  status: LiteLLMStatus = { running: false, port: null, last_error: null };
  private unlisten?: UnlistenFn;

  async fetchStatus(): Promise<void> {
    try {
      const s = await invoke<LiteLLMStatus>('get_litellm_status');
      this.status = s || { running: false, port: null, last_error: null };
    } catch (_) {
      this.status = { running: false, port: null };
    }
  }

  async ngOnInit(): Promise<void> {
    await this.fetchStatus();
    this.unlisten = await listen<LiteLLMStatus>('litellm-status', (event) => {
      const p = event.payload as LiteLLMStatus;
      this.status = p || { running: false, port: null, last_error: null };
    });
  }

  ngOnDestroy(): void {
    if (this.unlisten) this.unlisten();
  }

  get title(): string {
    return this.status.running
      ? `LiteLLM: running on ${this.status.port ?? 4000}`
      : 'LiteLLM: stopped';
  }
}

