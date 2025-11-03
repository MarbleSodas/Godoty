import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Command } from '../../models/command.model';

@Component({
  selector: 'app-command-history',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './command-history.component.html',
  styleUrls: ['./command-history.component.css']
})
export class CommandHistoryComponent {
  @Input() commands: Command[] = [];

  formatTime(date: Date): string {
    return date.toLocaleTimeString();
  }

  getStatusIcon(status: Command['status']): string {
    switch (status) {
      case 'success':
        return '✅';
      case 'error':
        return '❌';
      case 'pending':
        return '⏳';
    }
  }
}

