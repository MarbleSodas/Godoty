import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-command-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './command-input.component.html',
  styleUrls: ['./command-input.component.css']
})
export class CommandInputComponent {
  @Input() disabled: boolean = false;
  @Output() submitCommand = new EventEmitter<string>();

  input: string = '';

  handleSubmit(event: Event): void {
    event.preventDefault();
    if (this.input.trim() && !this.disabled) {
      this.submitCommand.emit(this.input.trim());
      this.input = '';
    }
  }
}

