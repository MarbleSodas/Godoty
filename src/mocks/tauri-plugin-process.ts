// Mock for @tauri-apps/plugin-process
export async function relaunch() {
  console.log('[Mock] plugin-process relaunch');
  (window as any).__IPC_CALLS__ = (window as any).__IPC_CALLS__ || [];
  (window as any).__IPC_CALLS__.push({ cmd: 'plugin:process|relaunch', args: {} });
}
