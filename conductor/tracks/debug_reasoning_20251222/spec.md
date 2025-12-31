# Specification: Debug and Enhance Reasoning Display

## 1. Overview
The goal of this track is to fix issues where the frontend (Vue/Tauri) fails to properly display the reasoning and thought processes of the AI agents. Additionally, we need to investigate and debug the reasoning capabilities of the Agno-based agents in the Python backend to ensure they are generating and streaming high-quality thought traces.

## 2. Problem Statement
- **Frontend:** The "Thoughts" or "Reasoning" panel in the desktop application is either empty, not updating in real-time, or displaying unstructured data instead of clear reasoning steps.
- **Backend:** It is unclear if the Agno agents are correctly configured to emit reasoning events or if the format of these events matches what the frontend expects.

## 3. Goals
- **Frontend Display:** Ensure the desktop application accurately renders agent reasoning in real-time (streaming) with proper formatting (markdown/text).
- **Backend Logic:** Verify and fix Agno agent configurations to guarantee that reasoning steps are generated and transmitted via the JSON-RPC protocol.
- **Protocol Alignment:** Ensure the data structure for "reasoning" events is consistent between the Python brain and the TypeScript frontend.

## 4. Implementation Details

### 4.1 Backend (Python / Agno)
- **File:** `brain/app/agents/team.py` (and related agent files)
- **Task:** Verify `show_tool_calls`, `show_reasoning`, or equivalent Agno settings are enabled.
- **Task:** Check how reasoning chunks are captured in the streaming response and wrapped in the JSON-RPC format.

### 4.2 Frontend (TypeScript / Vue)
- **File:** `desktop/src/components/ThoughtsPanel.vue` (or similar)
- **Task:** Debug the receipt of reasoning events.
- **Task:** Ensure the Vue component updates reactivity when new reasoning chunks arrive.

## 5. Acceptance Criteria
- [ ] Launching a complex query (e.g., "Plan a new feature") triggers visible reasoning in the "Thoughts" panel.
- [ ] Reasoning updates in real-time as the agent thinks.
- [ ] The final output is separate from the reasoning/thoughts.
- [ ] No console errors in the desktop debug console regarding missing fields or parsing failures.
