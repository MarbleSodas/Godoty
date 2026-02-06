// Mock for @tauri-apps/plugin-shell
export class Command {
  constructor(public cmd: string, public args: string[] = []) {}
  
  static create(cmd: string, args: string[] = []) {
    return new Command(cmd, args);
  }

  async spawn() {
    console.log('[Mock] plugin-shell spawn', this.cmd, this.args);
    (window as any).__IPC_CALLS__ = (window as any).__IPC_CALLS__ || [];
    (window as any).__IPC_CALLS__.push({ cmd: 'plugin:shell|spawn', args: { cmd: this.cmd, args: this.args } });
    return { pid: 123 };
  }

  async execute() {
    console.log('[Mock] plugin-shell execute', this.cmd, this.args);
    (window as any).__IPC_CALLS__ = (window as any).__IPC_CALLS__ || [];
    (window as any).__IPC_CALLS__.push({ cmd: 'plugin:shell|execute', args: { cmd: this.cmd, args: this.args } });
    return { code: 0, stdout: '', stderr: '' };
  }
}
