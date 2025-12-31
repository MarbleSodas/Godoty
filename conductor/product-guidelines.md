# Product Guidelines

## Prose Style
- **Concise & Technical:** All agent communications and system messages should prioritize brevity and technical precision.
- **Direct Action:** Agents should state what they intend to do clearly, using technical terminology appropriate for the Godot Engine and game development.
- **Minimal Filler:** Avoid conversational fluff and repetitive pleasantries.

## Communication & Reasoning
- **Proactive Clarification:** When faced with ambiguous requirements or complex architectural decisions, agents MUST halt and ask the user for clarification.
- **Collaborative Transparency:** The multi-agent team should clearly communicate their handoffs (e.g., "Architect proposing structure to Coder") to keep the user informed of the internal workflow.
- **Explicit Reasoning:** For major changes, agents should briefly state the technical rationale (the "why") behind their approach.

## User Interaction (HITL)
- **Safety First:** No file modifications or destructive actions may be taken without explicit user approval.
- **Clear Previews:** Proposed changes (code diffs, file creations) must be presented in a way that is easy for the user to review and verify.
- **Non-Intrusive Guidance:** Provide help and suggestions when requested, but allow the user to remain the ultimate authority over the project's direction.

## Visual Identity & UI Principles
- **Information Density:** The desktop interface should prioritize technical transparency, showing agent thoughts, tool logs, and status metrics without overwhelming the user.
- **Real-time Feedback:** Provide immediate visual cues for background activity, such as agent "thinking" states, WebSocket connection status, and progress indicators for long-running tasks.
- **Consistent Terminology:** Use standard Godot Engine nomenclature (Nodes, Scenes, GDScript, Resources) consistently throughout the UI and agent communications.

## Brand Messaging
- **Godoty as an Extension:** Position the tool as a powerful extension of the developer's own capabilities, not a replacement for their expertise.
- **Local-First Reliability:** Emphasize the privacy, security, and speed benefits of the local-sidecar architecture.
