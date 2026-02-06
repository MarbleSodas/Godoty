# Draft: Frontend Fixes + Godoty Theming

## Current Understanding

### Tech Stack
- **Framework**: SolidJS (v1.9.10)
- **Desktop**: Tauri v2
- **Styling**: Tailwind CSS v4
- **Build**: Vite v6
- **Structure**: Monorepo with packages:
  - `@opencode-ai/app` - main app logic, pages, routing
  - `@opencode-ai/ui` - UI components, theming system
  - `@opencode-ai/sdk` - SDK for backend communication

### Theming System
- Theme files: `packages/ui/src/theme/themes/oc-1.json`
- Theme provider: `packages/ui/src/theme/context.tsx`
- Uses CSS variables for dynamic theming
- Supports light/dark modes with system preference detection

### Desktop Entry Point
- `src/App.tsx` - wraps the app with PlatformProvider
- Platform object provides: `openLink`, `back`, `forward`, `restart`, `notify`
- Currently uses hardcoded Tailwind classes that may conflict with theme system

### Potential Issues Identified
1. `src/App.tsx` uses hardcoded Tailwind classes (`bg-gray-50`, `dark:bg-gray-900`) instead of theme CSS variables
2. Platform object may be missing desktop-specific features
3. "Godoty" branding may need to be more prominent throughout

## Open Questions
- What specific frontend issues need fixing?
- Which opencode desktop features aren't being utilized properly?
- What should "Godoty theming" look like? (colors, branding, etc.)
- Are there specific components that need attention?

## Research Findings
(To be populated during interview)

## Scope Boundaries
- INCLUDE: (TBD)
- EXCLUDE: (TBD)
