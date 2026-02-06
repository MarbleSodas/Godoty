import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/server.js', () => ({
  handleRunProject: vi.fn(),
  handleStopProject: vi.fn(),
}));

import { handleRunProject, handleStopProject } from '../../src/server.js';

describe('project execution tools', () => {
  describe('run_project', () => {
    it('should run project with optional scene', async () => {
      const mockHandle = vi.mocked(handleRunProject);
      mockHandle.mockImplementation(async (args: any) => {
        if (!args?.project_path) throw new Error('project_path is required');
        return { content: [{ type: 'text', text: 'Project started' }] };
      });

      const result = await handleRunProject({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn'
      });

      expect(result.content[0].text).toContain('Project started');
      expect(mockHandle).toHaveBeenCalledWith(expect.objectContaining({
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn'
      }));
    });

    it('should fail if project_path is missing', async () => {
      await expect(handleRunProject({}))
        .rejects.toThrow();
    });
  });

  describe('stop_project', () => {
    it('should stop a running project', async () => {
      const mockHandle = vi.mocked(handleStopProject);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Project stopped' }] });

      const result = await handleStopProject({ project_path: '/path/to/project' });
      expect(result.content[0].text).toContain('Project stopped');
      expect(mockHandle).toHaveBeenCalled();
    });
  });
});
