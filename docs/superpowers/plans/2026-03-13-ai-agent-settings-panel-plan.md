# AI Agent Settings Panel Redesign - Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dropdown-based provider selection with card-based UI, make model read-only, and show Base URL only for Custom provider.

**Architecture:** Modify existing AISettingsPanel to use toggle buttons (cards) for provider selection instead of OptionButton dropdown. Replace model LineEdit with read-only Label. Add conditional visibility for Base URL row.

**Tech Stack:** C++ (Godot Editor), Godot UI system (SceneTree)

**Spec Reference:** `docs/superpowers/specs/2026-03-13-ai-agent-config-ui-design.md`

---

## File Structure

| File | Changes |
|------|---------|
| `modules/ai_agent/editor/ai_settings_panel.h` | Add new widget members for cards and base URL visibility |
| `modules/ai_agent/editor/ai_settings_panel.cpp` | Complete UI redesign - card-based selection, read-only model, conditional base URL |

---

## Chunk 1: Header and Provider Cards

### Task 1: Update Header Declarations

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.h:21-53`

- [ ] **Step 1: Add new member variables to header**

Read the current header file to understand existing members, then add:

```cpp
// Add these new members after existing declarations (around line 30)
Vector<Button *> provider_cards;
HBoxContainer *base_url_container = nullptr;
Label *selected_model_label = nullptr;
LineEdit *base_url_input = nullptr;
int selected_provider_index = 0;

// Add these new method declarations
void _create_provider_cards();
void _on_card_selected(int p_index);
void _update_base_url_visibility();
```

- [ ] **Step 2: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.h
git commit -m "feat(ai_agent): add provider card members to AISettingsPanel"
```

---

### Task 2: Create Provider Cards in Constructor

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp:75-208`

- [ ] **Step 1: Read current constructor implementation**

Note the current structure and identify where provider cards should replace the dropdown.

- [ ] **Step 2: Replace dropdown with card container**

Find the section with `provider_select = memnew(OptionButton)` and replace with card creation code:

```cpp
// Replace the OptionButton section (lines 115-124) with:
VBoxContainer *cards_container = memnew(VBoxContainer);
cards_container->add_theme_constant_override("separation", 8 * EDSCALE);
setup_content->add_child(cards_container);

_create_provider_cards(); // This will populate provider_cards vector
```

- [ ] **Step 3: Implement _create_provider_cards method**

Add this method before the constructor or after _bind_methods:

```cpp
void AISettingsPanel::_create_provider_cards() {
    // Find the cards container (created in constructor)
    VBoxContainer *cards_container = nullptr;
    for (int i = 0; i < get_child_count(); i++) {
        Node *child = get_child(i);
        if (child->get_class() == "PanelContainer") {
            PanelContainer *pc = Object::cast_to<PanelContainer>(child);
            if (pc->get_child_count() > 0) {
                MarginContainer *mc = Object::cast_to<MarginContainer>(pc->get_child(0));
                if (mc && mc->get_child_count() > 0) {
                    VBoxContainer *vbc = Object::cast_to<VBoxContainer>(mc->get_child(0));
                    if (vbc && vbc->get_child_count() > 5) { // Has multiple children
                        cards_container = vbc;
                        break;
                    }
                }
            }
        }
    }

    if (!cards_container) {
        return;
    }

    // Clear any existing cards
    for (Button *btn : provider_cards) {
        btn->queue_free();
    }
    provider_cards.clear();

    // Create card for each provider
    for (int i = 0; i < 5; i++) {
        Button *card = memnew(Button);
        card->set_toggle_mode(true);
        card->set_button_group(nullptr); // Each is independent, we'll manage selection manually
        card->connect("pressed", callable_mp(this, &AISettingsPanel::_on_card_selected));
        card->set_meta("provider_index", i);

        // Card layout: HBox with icon, name, tagline
        HBoxContainer *card_layout = memnew(HBoxContainer);
        card_layout->add_theme_constant_override("separation", 12 * EDSCALE);
        card->add_child(card_layout);

        // Provider icon (colored rect)
        PanelContainer *icon_bg = memnew(PanelContainer);
        icon_bg->set_custom_minimum_size(Size2(24 * EDSCALE, 24 * EDSCALE));
        card_layout->add_child(icon_bg);

        Color provider_color;
        String provider_letter;
        switch (i) {
            case 0: provider_color = Color(0.063, 0.635, 0.498); provider_letter = "O"; break; // OpenAI green
            case 1: provider_color = Color(0.851, 0.467, 0.341); provider_letter = "A"; break; // Anthropic
            case 2: provider_color = Color(0.976, 0.725, 0.188); provider_letter = "M"; break; // MiniMax
            case 3: provider_color = Color(0.2, 0.2, 0.2); provider_letter = "L"; break; // Local
            case 4: provider_color = Color(0.4, 0.4, 0.4); provider_letter = "C"; break; // Custom
        }
        icon_bg->add_theme_color_override("panel_color", provider_color);

        Label *letter = memnew(Label);
        letter->set_text(provider_letter);
        letter->set_horizontal_alignment(HORIZONTAL_ALIGNMENT_CENTER);
        icon_bg->add_child(letter);

        // Name and tagline
        VBoxContainer *text_layout = memnew(VBoxContainer);
        card_layout->add_child(text_layout);

        Label *name = memnew(Label);
        name->set_text(ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i).name);
        name->add_theme_font_size_override("font_size", int(14 * EDSCALE));
        text_layout->add_child(name);

        Label *tagline = memnew(Label);
        tagline->set_text(ai_agent_get_provider_descriptor((AIAgentConfig::ProviderType)i).description);
        tagline->add_theme_color_override("font_color", get_theme_color("font_placeholder_color", "Editor"));
        tagline->add_theme_font_size_override("font_size", int(11 * EDSCALE));
        text_layout->add_child(tagline);

        // Add to container and tracking vector
        cards_container->add_child(card);
        provider_cards.push_back(card);
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): add provider card creation to settings panel"
```

---

### Task 3: Handle Card Selection

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Implement _on_card_selected handler**

Add after existing `_on_provider_changed`:

```cpp
void AISettingsPanel::_on_card_selected(int p_index) {
    // Update visual selection state
    for (int i = 0; i < provider_cards.size(); i++) {
        if (provider_cards[i]) {
            provider_cards[i]->set_pressed(i == p_index);
        }
    }

    selected_provider_index = p_index;

    // Update config
    if (config.is_valid()) {
        config->set_provider_type((AIAgentConfig::ProviderType)p_index);
        config->apply_provider_defaults(true, true); // Force model to default
    }

    // Update UI
    if (model_input) {
        model_input->set_text(config->get_model_name());
    }
    if (selected_model_label) {
        selected_model_label->set_text(config->get_model_name());
    }

    _refresh_provider_ui();
    _update_base_url_visibility();
}
```

- [ ] **Step 2: Add _update_base_url_visibility method**

```cpp
void AISettingsPanel::_update_base_url_visibility() {
    if (base_url_container) {
        bool is_custom = (selected_provider_index == AIAgentConfig::PROVIDER_CUSTOM);
        base_url_container->set_visible(is_custom);
    }
}
```

- [ ] **Step 3: Connect signals in constructor**

After creating cards, add:

```cpp
// In constructor, after _create_provider_cards() call:
// The card buttons are already connected via _on_card_selected in the loop
```

- [ ] **Step 4: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): add card selection and base URL visibility handlers"
```

---

## Chunk 2: Model Display and Base URL

### Task 4: Convert Model Input to Read-Only Label

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Find model input section in constructor**

Locate lines 148-170 where model_input is created.

- [ ] **Step 2: Replace LineEdit with Label**

Replace the entire model row section:

```cpp
// OLD (lines 148-170):
/*
{
    HBoxContainer *row = memnew(HBoxContainer);
    row->add_theme_constant_override("separation", 10 * EDSCALE);
    setup_content->add_child(row);

    Label *lbl = memnew(Label);
    lbl->set_text("Model");
    lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
    row->add_child(lbl);

    model_input = memnew(LineEdit);
    model_input->set_h_size_flags(SIZE_EXPAND_FILL);
    row->add_child(model_input);

    model_preset_button = memnew(MenuButton);
    model_preset_button->set_text("Browse");
    model_preset_button->get_popup()->connect("id_pressed", callable_mp(this, &AISettingsPanel::_on_model_preset_selected));
    row->add_child(model_preset_button);
}
*/

// NEW:
{
    HBoxContainer *row = memnew(HBoxContainer);
    row->add_theme_constant_override("separation", 10 * EDSCALE);
    setup_content->add_child(row);

    Label *lbl = memnew(Label);
    lbl->set_text("Model");
    lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
    row->add_child(lbl);

    selected_model_label = memnew(Label);
    selected_model_label->set_h_size_flags(SIZE_EXPAND_FILL);
    selected_model_label->set_text(config.is_valid() ? config->get_model_name() : "gpt-5-mini");
    row->add_child(selected_model_label);
}
```

- [ ] **Step 3: Update _refresh_provider_ui to handle label**

Modify `_refresh_provider_ui` to update the label instead of LineEdit:

```cpp
// In _refresh_provider_ui, find the section that updates model_input and add:
if (selected_model_label) {
    selected_model_label->set_text(default_model);
}
```

- [ ] **Step 4: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): convert model input to read-only label"
```

---

### Task 5: Add Conditional Base URL Display

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Find base URL section in constructor**

Locate lines 172-186 where base_url_input is created.

- [ ] **Step 2: Wrap in container and hide by default**

Replace the base URL section:

```cpp
// OLD (lines 172-186):
/*
{
    HBoxContainer *row = memnew(HBoxContainer);
    row->add_theme_constant_override("separation", 10 * EDSCALE);
    setup_content->add_child(row);

    Label *lbl = memnew(Label);
    lbl->set_text("Base URL");
    lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
    row->add_child(lbl);

    base_url_input = memnew(LineEdit);
    base_url_input->set_placeholder("Leave blank to use the provider default");
    base_url_input->set_h_size_flags(SIZE_EXPAND_FILL);
    row->add_child(base_url_input);
}
*/

// NEW:
base_url_container = memnew(HBoxContainer);
base_url_container->add_theme_constant_override("separation", 10 * EDSCALE);
base_url_container->set_visible(false); // Hidden by default
setup_content->add_child(base_url_container);

{
    Label *lbl = memnew(Label);
    lbl->set_text("Base URL");
    lbl->set_custom_minimum_size(Size2(110 * EDSCALE, 0));
    base_url_container->add_child(lbl);

    base_url_input = memnew(LineEdit);
    base_url_input->set_placeholder("https://api.example.com/v1");
    base_url_input->set_h_size_flags(SIZE_EXPAND_FILL);
    base_url_container->add_child(base_url_input);
}
```

- [ ] **Step 3: Initialize selected_provider_index**

Add after config instantiation:

```cpp
config.instantiate();
config->apply_provider_defaults(true, true);
selected_provider_index = (int)config->get_provider_type(); // Add this line
_apply_theme();
```

- [ ] **Step 4: Call _update_base_url_visibility in constructor**

Add at the end of constructor before `_apply_theme()`:

```cpp
_update_base_url_visibility();
```

- [ ] **Step 5: Update _load_config to set initial selection**

After loading provider type from settings:

```cpp
// After setting provider type in _load_config:
selected_provider_index = (int)config->get_provider_type();
_update_base_url_visibility();

// Update card visual state
for (int i = 0; i < provider_cards.size(); i++) {
    if (provider_cards[i]) {
        provider_cards[i]->set_pressed(i == selected_provider_index);
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): add conditional base URL display for Custom provider"
```

---

## Chunk 3: Integration and Styling

### Task 6: Update _save_config for New Structure

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Find _save_config method**

Locate lines 308-326.

- [ ] **Step 2: Update to use selected_provider_index**

Replace the provider type assignment:

```cpp
// OLD:
config->set_provider_type((AIAgentConfig::ProviderType)provider_select->get_selected_id());

// NEW:
config->set_provider_type((AIAgentConfig::ProviderType)selected_provider_index);
```

- [ ] **Step 3: Add base URL save**

After setting base_url:

```cpp
config->set_base_url(base_url_input ? base_url_input->get_text().strip_edges() : String());
```

- [ ] **Step 4: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): update save_config for card selection"
```

---

### Task 7: Remove Old Dropdown Code

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Remove provider_select dropdown**

Search for `provider_select` and remove all references:
- Declaration in header (but keep variable for now - it's used in _load_config)
- Creation in constructor
- Connection in constructor

- [ ] **Step 2: Remove model_preset_button**

Remove the MenuButton creation and all references to `model_preset_button`.

- [ ] **Step 3: Clean up _refresh_model_presets**

Since we're not using presets anymore (model is read-only), either remove or simplify this method.

- [ ] **Step 4: Update _load_config**

Replace dropdown selection code with card selection:

```cpp
// OLD (lines 357-362):
for (int i = 0; i < provider_select->get_item_count(); i++) {
    if (provider_select->get_item_id(i) == (int)config->get_provider_type()) {
        provider_select->select(i);
        break;
    }
}

// NEW:
selected_provider_index = (int)config->get_provider_type();
for (int i = 0; i < provider_cards.size(); i++) {
    if (provider_cards[i]) {
        provider_cards[i]->set_pressed(i == selected_provider_index);
    }
}
```

- [ ] **Step 5: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp modules/ai_agent/editor/ai_settings_panel.h
git commit -m "refactor(ai_agent): remove dropdown code, use card selection"
```

---

### Task 8: Add Card Styling

**Files:**
- Modify: `modules/ai_agent/editor/ai_settings_panel.cpp`

- [ ] **Step 1: Update _apply_theme**

Add card styling:

```cpp
void AISettingsPanel::_apply_theme() {
    Color accent = get_theme_color("accent_color", "Editor");
    Color muted = get_theme_color("font_placeholder_color", "Editor");

    if (provider_summary_label) {
        provider_summary_label->add_theme_color_override("font_color", accent);
    }
    if (api_key_hint_label) {
        api_key_hint_label->add_theme_color_override("font_color", muted);
    }
    if (model_hint_label) {
        model_hint_label->add_theme_color_override("font_color", muted);
    }

    // Add card styling
    for (Button *card : provider_cards) {
        if (card) {
            // Selected state
            Color card_bg = get_theme_color("button_pressed_color", "Editor");
            card->add_theme_color_override("font_color", card_bg);
        }
    }
}
```

- [ ] **Step 2: Add selected card visual feedback**

In `_on_card_selected`, add:

```cpp
// After updating pressed state:
Color selected_color = get_theme_color("accent_color", "Editor");
for (int i = 0; i < provider_cards.size(); i++) {
    if (provider_cards[i]) {
        if (i == p_index) {
            provider_cards[i]->add_theme_color_override("font_color", selected_color);
        } else {
            provider_cards[i]->remove_theme_color_override("font_color");
        }
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add modules/ai_agent/editor/ai_settings_panel.cpp
git commit -m "feat(ai_agent): add card selection styling"
```

---

## Testing Checklist

- [ ] Build the editor: `scons -j$(nproc) platform=macos`
- [ ] Open Godoty editor
- [ ] Navigate to AI Agent settings panel (right panel)
- [ ] Verify provider cards are displayed vertically
- [ ] Click each provider card and verify model label updates
- [ ] Select "Custom" provider and verify Base URL field appears
- [ ] Select other providers and verify Base URL field hides
- [ ] Enter API key and click Connect
- [ ] Verify configuration saves
- [ ] Restart editor and verify configuration persists

---

## Notes

- Provider cards use toggle buttons with manual selection management
- Model is now read-only - user sees default but cannot edit
- Base URL visibility controlled by _update_base_url_visibility()
- Icon colors match provider branding (OpenAI green, Anthropic orange, etc.)
