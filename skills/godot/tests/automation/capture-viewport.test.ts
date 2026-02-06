import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GodotHandler } from '../../src/server.js';
import * as child_process from 'child_process';
import * as fs from 'fs';

// Mock fs
vi.mock('fs', () => ({
  existsSync: vi.fn(),
  readdirSync: vi.fn(),
  readFileSync: vi.fn(),
}));

// Mock child_process
vi.mock('child_process', () => ({
  exec: vi.fn(),
  spawn: vi.fn(),
}));

describe('GodotHandler.captureViewport', () => {
  let handler: GodotHandler;
  const mockExec = vi.mocked(child_process.exec);
  const mockExistsSync = vi.mocked(fs.existsSync);

  beforeEach(() => {
    vi.clearAllMocks();
    handler = new GodotHandler();
    
    // Default mocks
    mockExistsSync.mockReturnValue(true);
    
    // Mock exec implementation to handle promisify(exec)
    // promisify(exec) calls exec(cmd, (err, stdout, stderr) => ...)
    mockExec.mockImplementation(((cmd: string, options: any, callback: any) => {
      if (typeof options === 'function') {
        callback = options;
      }
      
      // Handle version check
      if (cmd.includes('--version')) {
        callback(null, { stdout: '4.3.0', stderr: '' });
        return {} as any;
      }
      
      // Handle viewport capture
      if (cmd.includes('viewport_capture.gd')) {
        callback(null, { 
          stdout: 'Debug info...\nSCREENSHOT_PATH:/abs/path/to/viewport_2023.png\nMore info...', 
          stderr: '' 
        });
        return {} as any;
      }

      callback(null, { stdout: '', stderr: '' });
      return {} as any;
    }) as any);
  });

  it('should capture viewport and return path', async () => {
    const projectPath = '/absolute/project/path';
    
    // Force godotPath detection to succeed via mocks
    // The handler calls detectGodotPath internally if not set
    
    const result = await handler.captureViewport(projectPath);
    
    expect(result).toBe('/abs/path/to/viewport_2023.png');
    
    // Verify command
    expect(mockExec).toHaveBeenCalledWith(
      expect.stringContaining('viewport_capture.gd'),
      expect.anything() // callback
    );
  });

  it('should throw error if path not found in output', async () => {
    const projectPath = '/absolute/project/path';
    
    mockExec.mockImplementation(((cmd: string, options: any, callback: any) => {
        if (typeof options === 'function') callback = options;
        if (cmd.includes('--version')) {
            callback(null, { stdout: '4.3.0', stderr: '' });
            return {} as any;
        }
        if (cmd.includes('viewport_capture.gd')) {
            callback(null, { stdout: 'Some output but no screenshot path', stderr: '' });
            return {} as any;
        }
        callback(null, { stdout: '', stderr: '' });
        return {} as any;
    }) as any);

    await expect(handler.captureViewport(projectPath))
      .rejects
      .toThrow('Failed to capture viewport');
  });
});
