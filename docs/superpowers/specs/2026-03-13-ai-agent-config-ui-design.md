# AI Agent Configuration UI Redesign - Design Spec

**Date:** 2026-03-13
**Status:** Draft
**Author:** Claude

## 1. Overview

Redesign the AI Agent configuration UI to improve user experience by:
- Simplifying the settings panel with card-based provider selection
- Auto-selecting provider defaults (model) without user configuration
- Hiding advanced options (temperature, max tokens, system prompts) from users
- Adding collapsible thinking display in chat panel
- Optimizing layout for vertical right panel (Inspector panel context)

## 2. Goals

1. **Simplify Configuration** - Users only need to configure: Provider, API Key, and optionally Model
2. **Auto-detect Sensible Defaults** - Temperature, max tokens, and system prompts are handled per-mode internally
3. **Modern Visual Design** - Card-based provider selection matching Kilo Code/Copilot aesthetics
4. **Vertical Panel Optimization** - Layout optimized for narrow vertical right panel
5. **Thinking Display** - Collapsible thinking blocks in chat panel

## 3. Current State Analysis

### Existing Architecture

- `AIAgentConfig` - Resource holding: provider_type, api_key, model_name, base_url
- `AIProviderDescriptor` - Static provider info: name, description, default_model, recommended_models
- `AIAgentModeProfile` - Per-mode settings: harness_prompt, temperature (0.0-0.1), preferred_max_output_tokens (4096-8192)
- `ai_agent_resolve_run_config()` - Merges config + mode profile at runtime

### What Already Works

- Model auto-switches when provider changes (via `apply_provider_defaults(true, true)`)
- Temperature and max_tokens are already hidden (handled per-mode internally)
- System prompts are hidden (stored in `harness_prompt`, not exposed in UI)

### What Needs Changes

1. Settings Panel UI - Card-based provider selection
2. Chat Panel UI - Collapsible thinking display
3. Remove temperature/max_tokens fields from UI (already handled internally)
4. Simplify to only show: Provider, API Key, Model (read-only default), Base URL (Custom only)

## 4. UI/UX Specification

### 4.1 Settings Panel Layout

**Container:** Vertical right panel (width ~300px typical)

```
┌─────────────────────────────┐
│  Connect AI                │
│  Choose a provider         │
├─────────────────────────────┤
│  ┌─────────────────────┐   │
│  │  🟢 OpenAI    ✓   │   │
│  │  Default for coding│   │
│  └─────────────────────┘   │
│  ┌─────────────────────┐   │
│  │  🔵 Anthropic      │   │
│  │  Strong reasoning  │   │
│  └─────────────────────┘   │
│  ┌─────────────────────┐   │
│  │  🟡 MiniMax       │   │
│  │  OpenAI-compatible │   │
│  └─────────────────────┘   │
│  ┌─────────────────────┐   │
│  │  🐳 Local (Ollama) │   │
│  │  Run locally       │   │
│  └─────────────────────┘   │
│  ┌─────────────────────┐   │
│  │  ⚙️ Custom         │   │
│  │  Custom endpoint   │   │
│  └─────────────────────┘   │
├─────────────────────────────┤
│  API Key                   │
│  [••••••••••••••••••]      │
│                             │
│  Model: gpt-5-mini         │
│  (auto-selected)           │
│                             │
│  [Connect]                 │
└─────────────────────────────┘
```

**Component Specifications:**

| Component | Type | Behavior |
|-----------|------|----------|
| Provider Cards | Custom PanelContainer | Stacked vertically, click to select, shows checkmark on selected |
| Provider Icon | ColorRect + Emoji | Visual indicator per provider |
| Provider Name | Label | Bold, provider name |
| Provider Tagline | Label | Small, muted text (1 line max) |
| API Key Input | LineEdit (secret) | Full width, placeholder shows "sk-..." etc. |
| Model Display | Label | Shows current default model, read-only |
| Connect Button | Button | Primary action, bottom of panel |

**Provider Icons:**
- OpenAI: Green (#10A37F) - "G" or 🟢
- Anthropic: Blue (#D97757) - "A" or 🔵
- MiniMax: Yellow - "M" or 🟡
- Local: Dark - "Ollama" or 🐳
- Custom: Gray - ⚙️

### 4.2 Chat Panel Layout

**Container:** Vertical right panel with message list

```
┌─────────────────────────────┐
│  AI: Ask ▾                 │
├─────────────────────────────┤
│                             │
│  [User message]            │
│                             │
├─────────────────────────────┤
│  ▼ Thinking (2.3s)    [↕] │
│  ┌─────────────────────┐   │
│  │ Let me check the   │   │
│  │ project structure  │   │
│  │ first...            │   │
│  └─────────────────────┘   │
│  ─────────────────────────  │
│  Final response text       │
│  goes here...              │
│                             │
├─────────────────────────────┤
│  [Type a message...]    ↗  │
└─────────────────────────────┘
```

**Component Specifications:**

| Component | Type | Behavior |
|-----------|------|----------|
| Mode Dropdown | OptionButton | Select Ask/Edit/Plan mode |
| Thinking Header | Button (collapsible) | Shows "▼ Thinking (Xs)" with duration |
| Thinking Content | RichTextLabel | Indented, muted color, monospace optional |
| Divider | HSeparator | Thin line between thinking and response |
| Response | RichTextLabel | Normal chat styling |
| Input | TextEdit | Multi-line, send on Enter+Ctrl |

**Thinking Display Styling:**
- Background: Subtle highlight (#2A2A2A in dark theme)
- Text color: Muted (#888888)
- Font: Italic or smaller size
- Collapse state: Remembered per message
- Duration: Displayed in header when complete

### 4.3 Interaction Flows

**Provider Selection:**
1. User clicks provider card
2. Card shows checkmark indicator
3. Model label updates to new provider's default
4. API Key placeholder updates
5. No save needed - auto-applied

**Connect Flow:**
1. User enters API Key
2. Clicks "Connect"
3. Config saved to EditorSettings
4. Chat panel becomes active
5. Status shows "Connected to [Provider]"

**Thinking Display:**
1. When AI starts reasoning, thinking block appears
2. Thinking content streams in real-time
3. Header shows elapsed time
4. When complete, thinking collapses automatically OR stays expanded based on user toggle
5. Final response appears below divider

## 5. Technical Specification

### 5.1 Files to Modify

| File | Changes |
|------|---------|
| `modules/ai_agent/editor/ai_settings_panel.cpp` | Complete UI redesign - card-based provider selection |
| `modules/ai_agent/editor/ai_settings_panel.h` | Add new widget members |
| `modules/ai_agent/editor/ai_chat_panel.cpp` | Add thinking display components |
| `modules/ai_agent/editor/ai_chat_panel.h` | Add thinking-related members |
| `modules/ai_agent/ai_agent_mode.cpp` | Add thinking-related provider flags if needed |
| `modules/ai_agent/providers/*.cpp` | Ensure thinking content extraction |

### 5.2 New Components

**AISettingsPanel:**
- `Vector<PanelContainer*> provider_cards` - Card widgets
- `Label *selected_model_label` - Shows current model (read-only)
- `void _create_provider_cards()` - Build card UI
- `void _on_card_selected(int p_index)` - Handle selection

**AIChatPanel:**
- `PanelContainer *thinking_container` - Collapsible thinking block
- `RichTextLabel *thinking_content` - Thinking text display
- `Label *thinking_header` - "Thinking (Xs)" with collapse toggle
- `bool thinking_expanded` - Track collapse state
- `void _on_thinking_started()` - Show thinking block
- `void _on_thinking_chunk(String p_content)` - Stream thinking
- `void _on_thinking_complete()` - Update duration, auto-collapse
- `void _toggle_thinking()` - Manual collapse toggle

### 5.3 Data Flow

```
User clicks provider card
        ↓
_on_card_selected(int index)
        ↓
config->set_provider_type((ProviderType)index)
config->apply_provider_defaults(true, true)  // Force model to default
        ↓
Update UI:
  - provider_cards[i]->set_selected(index)
  - selected_model_label->set_text(config->get_model_name())
  - api_key_input->set_placeholder(config->get_api_key_placeholder())
        ↓
No explicit save needed - changes apply immediately
```

### 5.4 Message Handling for Thinking

**AIMessage Enhancement (if needed):**
```cpp
struct AIMessage {
    String role;
    String content;
    String thinking_content;  // New: reasoning/thinking text
    int thinking_duration_ms; // New: time spent thinking
    // ...
};
```

**Provider Updates:**
- OpenAI: `reasoning_content` field in responses (o1, o3 models)
- Anthropic: `thinking` block in messages (Claude 3.5+)
- MiniMax: Already has thinking support
- Local: Depends on model (Llama 3.1 has reasoning)

## 6. Compatibility Notes

### Backward Compatibility
- Existing EditorSettings keys preserved: `_ai_agent/provider_type`, `_ai_agent/api_key`, etc.
- If config exists, load and display current state
- Provider change still triggers model auto-switch

### Provider Descriptor Updates
- Add `supports_thinking` flag to `AIProviderDescriptor`
- Add `thinking_color` for UI theming
- Default thinking to collapsed for providers that support it

## 7. Acceptance Criteria

1. [ ] Settings panel shows provider cards instead of dropdown
2. [ ] Clicking a card selects provider and auto-updates model
3. [ ] Only API Key is required input; Model shows as read-only label
4. [ ] Base URL field hidden unless "Custom" provider selected
5. [ ] Temperature and max_tokens NOT shown in UI (already handled internally)
6. [ ] System prompt NOT shown in UI (already hidden)
7. [ ] Chat panel shows collapsible thinking block
8. [ ] Thinking shows duration and can be collapsed/expanded
9. [ ] Layout works in narrow vertical panel (~300px width)
10. [ ] Visual design matches modern card-based aesthetic

## 8. Future Considerations (Out of Scope)

- Provider-specific model recommendations dropdown
- Custom temperature/max_tokens for advanced users (behind toggle)
- Thinking streaming directly to UI
- Multiple simultaneous provider configurations
- Per-project provider overrides
