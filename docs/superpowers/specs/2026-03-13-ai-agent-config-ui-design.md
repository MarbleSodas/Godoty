# AI Agent Configuration UI Redesign - Design Spec

**Date:** 2026-03-13
**Status:** Revised (Phase 1: Settings Panel Approved)
**Author:** Claude

## 1. Overview

Redesign the AI Agent configuration UI to improve user experience by:
- Simplifying the settings panel with card-based provider selection (Phase 1)
- Auto-selecting provider defaults (model) without user configuration
- Hiding advanced options (temperature, max tokens, system prompts) from users
- Adding collapsible thinking display in chat panel (Phase 2 - deferred)
- Optimizing layout for vertical right panel (Inspector panel context)

## 2. Goals

1. **Simplify Configuration** - Users only need to configure: Provider, API Key. Model is auto-selected.
2. **Auto-detect Sensible Defaults** - Temperature, max tokens, and system prompts are handled per-mode internally
3. **Modern Visual Design** - Card-based provider selection matching Kilo Code/Copilot aesthetics
4. **Vertical Panel Optimization** - Layout optimized for narrow vertical right panel
5. **Thinking Display (Phase 2)** - Collapsible thinking blocks in chat panel (deferred)

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
- Recommended models are available via `config->get_recommended_models()`

### What Needs Changes

1. **Phase 1 - Settings Panel UI:**
   - Card-based provider selection (replace dropdown)
   - Model display as read-only label (no edit capability)
   - Base URL field hidden by default, shown only for Custom provider
   - Auto-apply model change on provider selection
   - Keep explicit "Connect" button for saving

2. **Phase 2 - Thinking Display (Deferred):**
   - Requires provider infrastructure updates
   - AIMessage enhancements for thinking_content
   - New signals in AIAgentSession
   - Will be specified in separate document

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
│  [Base URL (optional)]     │  <- Only shown for Custom
│                             │
│  [Connect]                 │
└─────────────────────────────┘
```

**Component Specifications:**

| Component | Type | Behavior |
|-----------|------|----------|
| Provider Cards | Button (toggle_mode) | Stacked vertically, click to select, shows checkmark on selected |
| Provider Icon | ColorRect | Visual indicator per provider (colored background) |
| Provider Name | Label | Bold, provider name |
| Provider Tagline | Label | Small, muted text (1 line max) |
| API Key Input | LineEdit (secret) | Full width, placeholder shows "sk-..." etc. |
| Model Display | Label | Shows current default model, **read-only - user cannot edit** |
| Base URL Input | LineEdit | Hidden by default, shown only when Custom provider selected |
| Connect Button | Button | Primary action, saves config to EditorSettings |

**Provider Icons:**
- OpenAI: Green (#10A37F) - "G" or 🟢
- Anthropic: Blue (#D97757) - "A" or 🔵
- MiniMax: Yellow - "M" or 🟡
- Local: Dark - "Ollama" or 🐳
- Custom: Gray - ⚙️

### 4.2 Chat Panel Layout (Phase 2 - Deferred)

> **Note:** This section is deferred to Phase 2. It requires:
> - Provider infrastructure updates to extract thinking content from API responses
> - AIMessage class enhancement with thinking_content field
> - New signals in AIAgentSession for thinking state
> - Will be specified in a separate design document

~~**Container:** Vertical right panel with message list~~

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
2. Card shows checkmark indicator (visual selection state)
3. Model label updates to new provider's default (read-only display)
4. API Key placeholder updates to provider-specific hint
5. Base URL field shows/hides based on provider (Custom only)
6. User must click "Connect" to save configuration

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

### 5.1 Files to Modify (Phase 1 Only)

| File | Changes |
|------|---------|
| `modules/ai_agent/editor/ai_settings_panel.cpp` | Complete UI redesign - card-based provider selection |
| `modules/ai_agent/editor/ai_settings_panel.h` | Add new widget members |

### 5.2 Files for Phase 2 (Deferred)

| File | Changes |
|------|---------|
| `modules/ai_agent/editor/ai_chat_panel.cpp` | Add thinking display components |
| `modules/ai_agent/editor/ai_chat_panel.h` | Add thinking-related members |
| `modules/ai_agent/ai_agent_mode.cpp` | Add thinking-related provider flags |
| `modules/ai_agent/ai_message.h` | Add thinking_content field |
| `modules/ai_agent/providers/*.cpp` | Extract thinking content from API responses |

### 5.2 New Components (Phase 1)

**AISettingsPanel:**
- `Vector<Button*> provider_cards` - Toggle buttons for each provider
- `Label *selected_model_label` - Shows current model (read-only)
- `HBoxContainer *base_url_container` - Hidden unless Custom provider
- `LineEdit *base_url_input` - Custom endpoint URL
- `void _create_provider_cards()` - Build card UI
- `void _on_card_selected(int p_index)` - Handle selection
- `void _update_base_url_visibility()` - Show/hide based on provider

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
  - provider_cards[i]->set_pressed(true) for selected
  - selected_model_label->set_text(config->get_model_name())
  - api_key_input->set_placeholder(config->get_api_key_placeholder())
  - base_url_container->set_visible(index == PROVIDER_CUSTOM)
        ↓
User clicks "Connect" to save → _save_config()
```

## 6. Compatibility Notes

### Backward Compatibility
- Existing EditorSettings keys preserved: `_ai_agent/provider_type`, `_ai_agent/api_key`, etc.
- If config exists, load and display current state
- Provider change still triggers model auto-switch

## 7. Acceptance Criteria

### Phase 1: Settings Panel Redesign

1. [ ] Settings panel shows provider cards instead of dropdown
2. [ ] Clicking a card selects provider and auto-updates model (read-only)
3. [ ] Only API Key is required input; Model shows as read-only label (no edit capability)
4. [ ] Base URL field hidden unless "Custom" provider selected
5. [ ] Temperature and max_tokens NOT shown in UI (already handled internally)
6. [ ] System prompt NOT shown in UI (already hidden)
7. [ ] User must click "Connect" button to save configuration
8. [ ] Layout works in narrow vertical panel (~300px width)
9. [ ] Visual design matches modern card-based aesthetic

### Phase 2: Thinking Display (Deferred)

10. [ ] Chat panel shows collapsible thinking block
11. [ ] Thinking shows duration and can be collapsed/expanded
12. [ ] Provider infrastructure updated to extract thinking content
13. [ ] AIMessage enhanced with thinking_content field

## 8. Future Considerations (Out of Scope)

- Provider-specific model recommendations dropdown
- Custom temperature/max_tokens for advanced users (behind toggle)
- **Thinking display** - See Phase 2 spec (separate document)
- Multiple simultaneous provider configurations
- Per-project provider overrides
