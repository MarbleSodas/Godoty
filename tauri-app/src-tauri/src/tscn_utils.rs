use anyhow::Result;
use std::fs;
use std::path::Path;

/// Minimal TSCN editor helpers used as a fallback when WebSocket actions fail.
/// NOTE: This is intentionally conservative and appends new nodes at the end of the file.
/// Godot will establish the hierarchy based on the `parent` attribute when the scene is (re)loaded.
pub fn add_node_to_tscn(scene_path: &str, node_name: &str, node_type: &str, parent_path: &str) -> Result<()> {
    let path = Path::new(scene_path);
    if !path.exists() {
        return Err(anyhow::anyhow!("Scene file not found: {}", scene_path));
    }

    let mut content = fs::read_to_string(path)?;

    // Basic sanitation of inputs to avoid breaking the tscn syntax
    let safe_name = sanitize_attr(node_name);
    let safe_type = sanitize_attr(node_type);
    let safe_parent = sanitize_attr(parent_path);

    // Append a new node block
    // Example: [node name="Title" type="Label" parent="MainMenu/Container"]
    let block = format!("\n[node name=\"{}\" type=\"{}\" parent=\"{}\"]\n", safe_name, safe_type, safe_parent);
    content.push_str(&block);

    fs::write(path, content)?;
    Ok(())
}

/// Returns true if the given node path already exists in the scene file (best-effort check).
pub fn tscn_has_node(scene_path: &str, node_path: &str) -> Result<bool> {
    let path = Path::new(scene_path);
    if !path.exists() {
        return Ok(false);
    }

    let content = fs::read_to_string(path)?;
    // Match either exact name at root or parent + name path
    let needle1 = format!("name=\"{}\"", node_path);
    let needle2 = format!("parent=\"{}\"", node_path);
    Ok(content.contains(&needle1) || content.contains(&needle2))
}

fn sanitize_attr(s: &str) -> String {
    s.replace('"', "'")
}

