import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/server.js', () => ({
  handleLaunchEditor: vi.fn(),
}));

import { handleLaunchEditor } from '../../src/server.js';

describe('launch_editor tool', () => {
  it('should validate project path', async () => {
    const mockHandle = vi.mocked(handleLaunchEditor);
    mockHandle.mockImplementation(async (args: any) => {
      if (!args?.project_path) throw new Error('project_path is required');
      return { content: [{ type: 'text', text: 'Editor launched' }] };
    });
    
    await expect(handleLaunchEditor({ project_path: '' }))
      .rejects.toThrow(/project_path/);
    
    const result = await handleLaunchEditor({ project_path: '/path/to/project' });
    expect(result.content[0].text).toContain('Editor launched');
    expect(mockHandle).toHaveBeenCalledWith({ project_path: '/path/to/project' });
  });

  it('should handle editor launch failures', async () => {
    const mockHandle = vi.mocked(handleLaunchEditor);
    mockHandle.mockRejectedValue(new Error('Failed to start Godot editor'));

    await expect(handleLaunchEditor({ project_path: '/path/to/project' }))
      .rejects.toThrow('Failed to start Godot editor');
  });
});
