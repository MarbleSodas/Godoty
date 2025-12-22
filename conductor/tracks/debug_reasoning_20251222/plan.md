# Implementation Plan - Debug Reasoning

## Phase 1: Diagnosis & Reproduction
- [ ] Task: Analyze Backend Agent Configuration
    - [ ] Sub-task: Inspect `brain/app/agents/team.py` to see how agents are initialized and if `reasoning` or `debug_mode` is enabled.
    - [ ] Sub-task: Check `brain/app/main.py` or the WebSocket handler to see how stream chunks are processed and sent to the client.
- [ ] Task: Analyze Frontend Event Handling
    - [ ] Sub-task: Inspect `desktop/src/stores/brain.ts` (or equivalent) to see how WebSocket messages are parsed.
    - [ ] Sub-task: Inspect `desktop/src/components/ThoughtsPanel.vue` to see how it binds to the data store.
- [ ] Task: Reproduce Issue
    - [ ] Sub-task: Run the app and trigger a request that requires reasoning. Log the raw WebSocket traffic to identify if the issue is transmission (missing data) or rendering (frontend bug).

## Phase 2: Backend Fixes (Agno & Protocol)
- [ ] Task: Enable/Fix Agent Reasoning
    - [ ] Sub-task: Modify Agno agent initialization to ensure `show_reasoning=True` (or equivalent).
    - [ ] Sub-task: Ensure the JSON-RPC notification for reasoning (e.g., `agent.thought`) is correctly formatted and distinct from the final content.
    - [ ] Sub-task: Write a small unit test or script `tests/test_reasoning_stream.py` to verify the backend emits reasoning events.

## Phase 3: Frontend Integration
- [ ] Task: Update Frontend Store
    - [ ] Sub-task: Update the Pinia store to correctly ingest `agent.thought` events and append them to the current message's reasoning state.
- [ ] Task: Fix ThoughtsPanel Component
    - [ ] Sub-task: Ensure the component watches the store correctly and auto-scrolls/updates as new thoughts arrive.
    - [ ] Sub-task: Improve styling if the current display is unreadable (e.g., handle markdown in thoughts if applicable).

## Phase 4: Verification
- [ ] Task: End-to-End Verification
    - [ ] Sub-task: Run the full stack (Tauri + Python).
    - [ ] Sub-task: Perform a "Lead Developer" query.
    - [ ] Sub-task: Confirm reasoning appears in the UI and matches the backend logs.
