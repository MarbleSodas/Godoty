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
  @Input() projectPath: string = '';
  @Output() saveApiKey = new EventEmitter<string>();
  @Output() saveProjectPath = new EventEmitter<string>();
  @Output() reconnect = new EventEmitter<void>();

  editingKey: boolean = false;
  editingPath: boolean = false;
  tempKey: string = '';
  tempPath: string = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['apiKey']) {
      this.tempKey = this.apiKey;
    }
    if (changes['projectPath']) {
      this.tempPath = this.projectPath;
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

  handleSavePath(): void {
    this.saveProjectPath.emit(this.tempPath);
    this.editingPath = false;
  }

  handleCancelPath(): void {
    this.tempPath = this.projectPath;
    this.editingPath = false;
  }

  handleReconnect(): void {
    this.reconnect.emit();
  }
}

