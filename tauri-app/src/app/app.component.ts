import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { invoke } from '@tauri-apps/api/core';
import { Command, ConnectionStatus } from './models/command.model';
import { CommandInputComponent } from './components/command-input/command-input.component';
import { CommandHistoryComponent } from './components/command-history/command-history.component';
import { StatusPanelComponent } from './components/status-panel/status-panel.component';
import { SettingsPanelComponent } from './components/settings-panel/settings-panel.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    CommandInputComponent,
    CommandHistoryComponent,
    StatusPanelComponent,
    SettingsPanelComponent
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit {
  commands: Command[] = [];
  connectionStatus: ConnectionStatus = 'disconnected';
  apiKey: string = '';

  ngOnInit(): void {
    this.loadApiKey();
    this.connectToGodot();
  }

  async loadApiKey(): Promise<void> {
    try {
      this.apiKey = await invoke<string>('get_api_key');
    } catch (error) {
      console.error('Failed to load API key:', error);
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

    try {
      const response = await invoke<string>('process_command', { input });
      this.commands = this.commands.map(cmd =>
        cmd.id === command.id
          ? { ...cmd, status: 'success', response }
          : cmd
      );
    } catch (error) {
      this.commands = this.commands.map(cmd =>
        cmd.id === command.id
          ? { ...cmd, status: 'error', response: String(error) }
          : cmd
      );
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
}

