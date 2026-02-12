# Plan: Suppress ResizeObserver Loop Error

## TL;DR
The application is now loading (Success!), but crashing with a "ResizeObserver loop completed with undelivered notifications" error. This is a common, often benign browser error caused by layout shifts during observation. We will update our error reporter to ignore this specific message to prevent the red screen of death.

## Diagnosis
- **Symptom**: Red error screen appears after some time.
- **Error**: "ResizeObserver loop completed with undelivered notifications."
- **Root Cause**: This occurs when a `ResizeObserver` callback itself triggers a layout change that requires another observation in the same frame. While the browser handles it, it emits an error that our new global error handler catches.
- **Fix**: Filter out this specific error string in the `index.html` error reporter.

## Work Objectives

### Concrete Deliverables
- [ ] Modified `packages/app/index.html`: Updated error handler to ignore `ResizeObserver` loop errors.

### Definition of Done
- [ ] `index.html` error reporter does not trigger for "ResizeObserver loop completed with undelivered notifications".
- [ ] Other real errors still trigger the red banner.

---

## TODOs

- [ ] 1. Update Error Reporter in index.html
  **What to do**:
  - Edit `packages/app/index.html`.
  - Update the `window.onerror` and `window.onunhandledrejection` handlers.
  - Add a check: `if (message && message.includes("ResizeObserver loop")) return;`.
  **Acceptance Criteria**:
  - [ ] Benign ResizeObserver errors are ignored.

---

## Success Criteria
- [ ] The application remains usable without the red error screen appearing for this specific observer warning.
