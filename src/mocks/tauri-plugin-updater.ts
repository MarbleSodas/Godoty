// Mock for @tauri-apps/plugin-updater
export async function check() {
  console.log('[Mock] plugin-updater check');
  const call = { cmd: 'plugin:updater|check', args: {} };
  (window as any).__IPC_CALLS__ = (window as any).__IPC_CALLS__ || [];
  (window as any).__IPC_CALLS__.push(call);
  
  return {
    available: true,
    version: '1.0.1',
    date: '2023-01-01',
    body: 'New features',
    downloadAndInstall: async () => {
       console.log('[Mock] downloadAndInstall');
       (window as any).__IPC_CALLS__.push({ cmd: 'plugin:updater|download_and_install', args: {} });
    }
  };
}
