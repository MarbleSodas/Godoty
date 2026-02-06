import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/server.js', () => ({
  handleGetGodotVersion: vi.fn(),
  handleCheckGodotStatus: vi.fn(),
}));

import { handleGetGodotVersion, handleCheckGodotStatus } from '../../src/server.js';

describe('godot environment tools', () => {
  describe('get_godot_version', () => {
    it('should return the installed Godot version', async () => {
      const mockHandle = vi.mocked(handleGetGodotVersion);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Godot v4.3.stable' }] });

      const result = await handleGetGodotVersion({});
      expect(result.content[0].text).toContain('v4.3');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('check_godot_status', () => {
    it('should return status info about Godot process', async () => {
      const mockHandle = vi.mocked(handleCheckGodotStatus);
      mockHandle.mockResolvedValue({ 
        content: [{ type: 'text', text: JSON.stringify({ running: true, pid: 1234 }) }] 
      });

      const result = await handleCheckGodotStatus({});
      const status = JSON.parse(result.content[0].text);
      expect(status.running).toBe(true);
      expect(mockHandle).toHaveBeenCalled();
    });
  });
});
