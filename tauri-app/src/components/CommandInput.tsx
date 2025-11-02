import { useState } from "react";
import "./CommandInput.css";

interface CommandInputProps {
  onSubmit: (input: string) => void;
  disabled?: boolean;
}

export function CommandInput({ onSubmit, disabled }: CommandInputProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSubmit(input.trim());
      setInput("");
    }
  };

  return (
    <div className="command-input-container">
      <h2>💬 Command Input</h2>
      <form onSubmit={handleSubmit} className="command-form">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe what you want to create in Godot...&#10;&#10;Example: Add a 2D player character with a sprite and collision shape"
          disabled={disabled}
          rows={4}
          className="command-textarea"
        />
        <button type="submit" disabled={disabled || !input.trim()} className="submit-button">
          {disabled ? "⏸ Not Ready" : "🚀 Execute"}
        </button>
      </form>
      {disabled && (
        <p className="warning-text">
          ⚠️ Please configure your API key and ensure Godot is connected
        </p>
      )}
    </div>
  );
}

