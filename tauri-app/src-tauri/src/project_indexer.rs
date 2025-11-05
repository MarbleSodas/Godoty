use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProjectIndex {
    pub scenes: Vec<SceneInfo>,
    pub scripts: Vec<ScriptInfo>,
    pub resources: Vec<ResourceInfo>,
    pub project_path: String,
    pub godot_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SceneInfo {
    pub path: String,
    pub name: String,
    pub root_type: Option<String>,
    pub nodes: Vec<NodeInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeInfo {
    pub name: String,
    pub node_type: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScriptInfo {
    pub path: String,
    pub name: String,
    pub content_preview: String, // First 500 chars
    pub classes: Vec<String>,
    pub functions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResourceInfo {
    pub path: String,
    pub name: String,
    pub resource_type: String,
}

pub struct ProjectIndexer {
    project_path: PathBuf,
}

impl ProjectIndexer {
    pub fn new(project_path: &str) -> Self {
        Self {
            project_path: PathBuf::from(project_path),
        }
    }

    pub fn index_project(&self) -> Result<ProjectIndex> {
        // Best-effort Godot version detection (optional)
        let godot_version = {
            let cfg = self.project_path.join("project.godot");
            if let Ok(content) = fs::read_to_string(cfg) {
                let mut found: Option<String> = None;
                for line in content.lines() {
                    let l = line.trim();
                    if l.starts_with("config_version=") {
                        found = Some("4.x".to_string());
                        break;
                    }
                    if l.contains("godot") && l.contains("version") {
                        found = Some(l.to_string());
                        break;
                    }
                }
                found
            } else { None }
        };

        let mut index = ProjectIndex {
            scenes: Vec::new(),
            scripts: Vec::new(),
            resources: Vec::new(),
            project_path: self.project_path.to_string_lossy().to_string(),
            godot_version,
        };

        // Index scenes (.tscn files)
        self.index_scenes(&self.project_path, &mut index)?;

        // Index scripts (.gd files)
        self.index_scripts(&self.project_path, &mut index)?;

        // Index resources (.tres files)
        self.index_resources(&self.project_path, &mut index)?;

        Ok(index)
    }

    fn index_scenes(&self, dir: &Path, index: &mut ProjectIndex) -> Result<()> {
        if !dir.is_dir() {
            return Ok(());
        }

        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.is_dir() {
                // Skip hidden directories and common ignore patterns
                if let Some(name) = path.file_name() {
                    let name_str = name.to_string_lossy();
                    if name_str.starts_with('.') || name_str == "addons" || name_str == ".godot" {
                        continue;
                    }
                }
                self.index_scenes(&path, index)?;
            } else if let Some(ext) = path.extension() {
                if ext == "tscn" {
                    if let Ok(scene_info) = self.parse_scene(&path) {
                        index.scenes.push(scene_info);
                    }
                }
            }
        }

        Ok(())
    }

    fn parse_scene(&self, path: &Path) -> Result<SceneInfo> {
        let content = fs::read_to_string(path)?;
        let name = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        let mut root_type = None;
        let mut nodes = Vec::new();

        // Parse the .tscn file to extract node information
        for line in content.lines() {
            if line.starts_with("[node") {
                // Extract node information
                if let Some(node_info) = self.parse_node_line(line) {
                    if root_type.is_none() {
                        root_type = Some(node_info.node_type.clone());
                    }
                    nodes.push(node_info);
                }
            }
        }

        Ok(SceneInfo {
            path: path.to_string_lossy().to_string(),
            name,
            root_type,
            nodes,
        })
    }

    fn parse_node_line(&self, line: &str) -> Option<NodeInfo> {
        // Example: [node name="Player" type="CharacterBody2D" parent="."]
        let mut name = String::new();
        let mut node_type = String::new();
        let mut parent = String::from(".");

        // Simple parsing - extract name and type
        if let Some(name_start) = line.find("name=\"") {
            let name_content = &line[name_start + 6..];
            if let Some(name_end) = name_content.find('"') {
                name = name_content[..name_end].to_string();
            }
        }

        if let Some(type_start) = line.find("type=\"") {
            let type_content = &line[type_start + 6..];
            if let Some(type_end) = type_content.find('"') {
                node_type = type_content[..type_end].to_string();
            }
        }

        if let Some(parent_start) = line.find("parent=\"") {
            let parent_content = &line[parent_start + 8..];
            if let Some(parent_end) = parent_content.find('"') {
                parent = parent_content[..parent_end].to_string();
            }
        }

        if !name.is_empty() && !node_type.is_empty() {
            Some(NodeInfo {
                name: name.clone(),
                node_type,
                path: if parent == "." {
                    name
                } else {
                    format!("{}/{}", parent, name)
                },
            })
        } else {
            None
        }
    }

    fn index_scripts(&self, dir: &Path, index: &mut ProjectIndex) -> Result<()> {
        if !dir.is_dir() {
            return Ok(());
        }

        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.is_dir() {
                if let Some(name) = path.file_name() {
                    let name_str = name.to_string_lossy();
                    if name_str.starts_with('.') || name_str == ".godot" {
                        continue;
                    }
                }
                self.index_scripts(&path, index)?;
            } else if let Some(ext) = path.extension() {
                if ext == "gd" {
                    if let Ok(script_info) = self.parse_script(&path) {
                        index.scripts.push(script_info);
                    }
                }
            }
        }

        Ok(())
    }

    fn parse_script(&self, path: &Path) -> Result<ScriptInfo> {
        let content = fs::read_to_string(path)?;
        let name = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        let content_preview = if content.len() > 500 {
            content.chars().take(500).collect()
        } else {
            content.clone()
        };

        let mut classes = Vec::new();
        let mut functions = Vec::new();

        // Parse GDScript to extract classes and functions
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("class_name ") {
                if let Some(class_name) = trimmed.strip_prefix("class_name ") {
                    classes.push(class_name.trim().to_string());
                }
            } else if trimmed.starts_with("func ") {
                if let Some(func_def) = trimmed.strip_prefix("func ") {
                    if let Some(paren_pos) = func_def.find('(') {
                        functions.push(func_def[..paren_pos].trim().to_string());
                    }
                }
            }
        }

        Ok(ScriptInfo {
            path: path.to_string_lossy().to_string(),
            name,
            content_preview,
            classes,
            functions,
        })
    }

    fn index_resources(&self, dir: &Path, index: &mut ProjectIndex) -> Result<()> {
        if !dir.is_dir() {
            return Ok(());
        }

        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.is_dir() {
                if let Some(name) = path.file_name() {
                    let name_str = name.to_string_lossy();
                    if name_str.starts_with('.') || name_str == ".godot" {
                        continue;
                    }
                }
                self.index_resources(&path, index)?;
            } else if let Some(ext) = path.extension() {
                if ext == "tres" {
                    if let Ok(resource_info) = self.parse_resource(&path) {
                        index.resources.push(resource_info);
                    }
                }
            }
        }

        Ok(())
    }

    fn parse_resource(&self, path: &Path) -> Result<ResourceInfo> {
        let content = fs::read_to_string(path)?;
        let name = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        let mut resource_type = String::from("Resource");

        // Extract resource type from the file
        for line in content.lines() {
            if line.starts_with("[gd_resource") || line.starts_with("[resource") {
                if let Some(type_start) = line.find("type=\"") {
                    let type_content = &line[type_start + 6..];
                    if let Some(type_end) = type_content.find('"') {
                        resource_type = type_content[..type_end].to_string();
                    }
                }
                break;
            }
        }

        Ok(ResourceInfo {
            path: path.to_string_lossy().to_string(),
            name,
            resource_type,
        })
    }
}

