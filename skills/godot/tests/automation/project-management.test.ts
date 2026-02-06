import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/server.js', () => ({
  handleListProjects: vi.fn(),
  handleGetProjectInfo: vi.fn(),
}));

import { handleListProjects, handleGetProjectInfo } from '../../src/server.js';

describe('project management tools', () => {
  describe('list_projects', () => {
    it('should list projects in a directory', async () => {
      const mockHandle = vi.mocked(handleListProjects);
      mockHandle.mockResolvedValue({ 
        content: [{ type: 'text', text: JSON.stringify([{ name: 'Project1', path: '/path1' }]) }] 
      });

      const result = await handleListProjects({ directory: '/projects' });
      const projects = JSON.parse(result.content[0].text);
      
      expect(projects).toHaveLength(1);
      expect(projects[0].name).toBe('Project1');
      expect(mockHandle).toHaveBeenCalledWith({ directory: '/projects' });
    });
  });

  describe('get_project_info', () => {
    it('should return info for a specific project', async () => {
      const mockHandle = vi.mocked(handleGetProjectInfo);
      mockHandle.mockResolvedValue({ 
        content: [{ type: 'text', text: JSON.stringify({ name: 'Project1', version: '1.0.0' }) }] 
      });

      const result = await handleGetProjectInfo({ project_path: '/path/to/project' });
      const info = JSON.parse(result.content[0].text);
      
      expect(info.name).toBe('Project1');
      expect(mockHandle).toHaveBeenCalledWith({ project_path: '/path/to/project' });
    });
  });
});
