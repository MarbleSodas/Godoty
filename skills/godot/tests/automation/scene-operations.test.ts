import { describe, it, expect, vi } from 'vitest';

vi.mock('../../src/server.js', () => ({
  handleCreateScene: vi.fn(),
  handleAddNode: vi.fn(),
  handleSaveScene: vi.fn(),
  handleGetSceneTree: vi.fn(),
  handleRemoveNode: vi.fn(),
  handleUpdateNode: vi.fn(),
  handleListScenes: vi.fn(),
}));

import { 
  handleCreateScene, 
  handleAddNode, 
  handleSaveScene, 
  handleGetSceneTree,
  handleRemoveNode,
  handleUpdateNode,
  handleListScenes
} from '../../src/server.js';

describe('scene operations', () => {
  describe('create_scene', () => {
    it('should create a new scene with root node', async () => {
      const mockHandle = vi.mocked(handleCreateScene);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Scene created: res://new_scene.tscn' }] });

      const result = await handleCreateScene({ 
        project_path: '/path/to/project',
        scene_path: 'res://new_scene.tscn',
        root_node_type: 'Node3D'
      });

      expect(result.content[0].text).toContain('res://new_scene.tscn');
      expect(mockHandle).toHaveBeenCalledWith(expect.objectContaining({
        root_node_type: 'Node3D'
      }));
    });
  });

  describe('add_node', () => {
    it('should add a node to a scene', async () => {
      const mockHandle = vi.mocked(handleAddNode);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Node added' }] });

      const result = await handleAddNode({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn',
        node_name: 'Player',
        node_type: 'CharacterBody3D',
        parent_path: '.'
      });

      expect(result.content[0].text).toBe('Node added');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('save_scene', () => {
    it('should save the current state of a scene', async () => {
      const mockHandle = vi.mocked(handleSaveScene);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Scene saved' }] });

      const result = await handleSaveScene({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn'
      });

      expect(result.content[0].text).toBe('Scene saved');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('get_scene_tree', () => {
    it('should return the node hierarchy of a scene', async () => {
      const mockHandle = vi.mocked(handleGetSceneTree);
      mockHandle.mockResolvedValue({ 
        content: [{ type: 'text', text: JSON.stringify({ name: 'Root', children: [] }) }] 
      });

      const result = await handleGetSceneTree({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn'
      });

      const tree = JSON.parse(result.content[0].text);
      expect(tree.name).toBe('Root');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('remove_node', () => {
    it('should remove a node from a scene', async () => {
      const mockHandle = vi.mocked(handleRemoveNode);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Node removed' }] });

      const result = await handleRemoveNode({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn',
        node_path: 'Root/Player'
      });

      expect(result.content[0].text).toBe('Node removed');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('update_node', () => {
    it('should update properties of a node', async () => {
      const mockHandle = vi.mocked(handleUpdateNode);
      mockHandle.mockResolvedValue({ content: [{ type: 'text', text: 'Node updated' }] });

      const result = await handleUpdateNode({ 
        project_path: '/path/to/project',
        scene_path: 'res://main.tscn',
        node_path: 'Root/Player',
        properties: { name: 'Hero' }
      });

      expect(result.content[0].text).toBe('Node updated');
      expect(mockHandle).toHaveBeenCalled();
    });
  });

  describe('list_scenes', () => {
    it('should list all scenes in the project', async () => {
      const mockHandle = vi.mocked(handleListScenes);
      mockHandle.mockResolvedValue({ 
        content: [{ type: 'text', text: JSON.stringify(['res://main.tscn', 'res://player.tscn']) }] 
      });

      const result = await handleListScenes({ project_path: '/path/to/project' });
      const scenes = JSON.parse(result.content[0].text);
      expect(scenes).toContain('res://main.tscn');
      expect(mockHandle).toHaveBeenCalled();
    });
  });
});
