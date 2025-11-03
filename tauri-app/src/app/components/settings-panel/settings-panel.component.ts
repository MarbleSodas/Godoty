import { Component, EventEmitter, Input, Output, OnChanges, SimpleChanges } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-settings-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings-panel.component.html',
  styleUrls: ['./settings-panel.component.css']
})
export class SettingsPanelComponent implements OnChanges {
  @Input() apiKey: string = '';
  @Output() saveApiKey = new EventEmitter<string>();
  @Output() reconnect = new EventEmitter<void>();

  editingKey: boolean = false;
  tempKey: string = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['apiKey']) {
      this.tempKey = this.apiKey;
    }
  }

  handleSave(): void {
    this.saveApiKey.emit(this.tempKey);
    this.editingKey = false;
  }

  handleCancel(): void {
    this.tempKey = this.apiKey;
    this.editingKey = false;
  }

  handleReconnect(): void {
    this.reconnect.emit();
  }
}

