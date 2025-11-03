import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConnectionStatus } from '../../models/command.model';

@Component({
  selector: 'app-status-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './status-panel.component.html',
  styleUrls: ['./status-panel.component.css']
})
export class StatusPanelComponent {
  @Input() status: ConnectionStatus = 'disconnected';

  getStatusIcon(): string {
    switch (this.status) {
      case 'connected':
        return '🟢';
      case 'connecting':
        return '🟡';
      case 'disconnected':
        return '🔴';
    }
  }

  getStatusText(): string {
    switch (this.status) {
      case 'connected':
        return 'Connected to Godot';
      case 'connecting':
        return 'Connecting...';
      case 'disconnected':
        return 'Disconnected';
    }
  }
}

