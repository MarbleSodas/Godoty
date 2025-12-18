"""Project context gathering for Godoty agents.

This module provides automatic context gathering from the connected Godot project,
including scene/node hierarchies, script dependencies, and class relationships.

Context is gathered when:
- Godot connects with a project (hello handshake)
- Explicitly requested via the get_project_context tool
- Invalidated by project changes (scene/script changes)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.tools import get_project_path


@dataclass
class ScriptInfo:
    """Information about a GDScript file."""
    path: str
    class_name: str | None = None
    extends: str | None = None
    dependencies: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    exported_vars: list[str] = field(default_factory=list)


@dataclass
class SceneInfo:
    """Information about a scene file."""
    path: str
    root_type: str | None = None
    root_name: str | None = None
    attached_script: str | None = None
    instance_count: int = 0


@dataclass
class ProjectContext:
    """Comprehensive context about the connected Godot project.
    
    Prioritizes:
    1. Scene/node hierarchies
    2. Script dependencies and class relationships
    """
    # Basic project info
    project_path: str
    project_name: str = ""
    godot_version: str = ""
    
    # Main entry points
    main_scene: str | None = None
    autoloads: dict[str, str] = field(default_factory=dict)  # name -> path
    
    # Scene structure (prioritized)
    scenes: list[SceneInfo] = field(default_factory=list)
    
    # Script relationships (prioritized)
    scripts: list[ScriptInfo] = field(default_factory=list)
    class_hierarchy: dict[str, list[str]] = field(default_factory=dict)  # base -> [derived]
    
    # Other resources (lower priority)
    resources: list[str] = field(default_factory=list)
    
    # Directory structure
    directories: list[str] = field(default_factory=list)


def _parse_project_godot(project_path: Path) -> dict[str, Any]:
    """Parse project.godot file for key settings.
    
    Returns:
        Dictionary with project_name, main_scene, autoloads, etc.
    """
    result: dict[str, Any] = {
        "project_name": "",
        "main_scene": None,
        "autoloads": {},
    }
    
    godot_file = project_path / "project.godot"
    if not godot_file.exists():
        return result
    
    try:
        content = godot_file.read_text(encoding="utf-8")
        
        # Parse [application] section for project name and main scene
        app_match = re.search(
            r'\[application\](.*?)(?=\n\[|\Z)',
            content,
            re.DOTALL
        )
        if app_match:
            app_section = app_match.group(1)
            
            # Project name
            name_match = re.search(r'config/name="([^"]+)"', app_section)
            if name_match:
                result["project_name"] = name_match.group(1)
            
            # Main scene
            scene_match = re.search(r'run/main_scene="([^"]+)"', app_section)
            if scene_match:
                result["main_scene"] = scene_match.group(1)
        
        # Parse [autoload] section
        autoload_match = re.search(
            r'\[autoload\](.*?)(?=\n\[|\Z)',
            content,
            re.DOTALL
        )
        if autoload_match:
            autoload_section = autoload_match.group(1)
            for line in autoload_section.strip().split('\n'):
                if '=' in line and not line.strip().startswith(';'):
                    parts = line.split('=', 1)
                    name = parts[0].strip()
                    # Parse: "*res://path/to/script.gd" (the * means enabled)
                    path_match = re.search(r'"[*]?(res://[^"]+)"', parts[1])
                    if path_match and name:
                        result["autoloads"][name] = path_match.group(1)
        
    except Exception:
        pass  # Silent fail - return partial results
    
    return result


def _parse_gdscript(content: str, file_path: str) -> ScriptInfo:
    """Parse a GDScript file for class info and dependencies.
    
    Extracts:
    - class_name declaration
    - extends clause
    - preload/load dependencies
    - signal declarations
    - exported variables
    """
    info = ScriptInfo(path=file_path)
    
    try:
        # Class name
        class_match = re.search(r'^class_name\s+(\w+)', content, re.MULTILINE)
        if class_match:
            info.class_name = class_match.group(1)
        
        # Extends
        extends_match = re.search(r'^extends\s+(\w+)', content, re.MULTILINE)
        if extends_match:
            info.extends = extends_match.group(1)
        
        # Dependencies (preload/load)
        for dep_match in re.finditer(r'(?:preload|load)\s*\(\s*"([^"]+)"', content):
            dep_path = dep_match.group(1)
            if dep_path not in info.dependencies:
                info.dependencies.append(dep_path)
        
        # Signals
        for sig_match in re.finditer(r'^signal\s+(\w+)', content, re.MULTILINE):
            info.signals.append(sig_match.group(1))
        
        # Exported variables (first 10)
        export_count = 0
        for exp_match in re.finditer(r'^@export[^\n]*var\s+(\w+)', content, re.MULTILINE):
            if export_count < 10:
                info.exported_vars.append(exp_match.group(1))
                export_count += 1
        
    except Exception:
        pass  # Silent fail - return partial results
    
    return info


def _parse_scene_file(content: str, file_path: str) -> SceneInfo:
    """Parse a .tscn scene file for structure info.
    
    Extracts:
    - Root node type and name
    - Attached script
    - Number of instanced scenes
    """
    info = SceneInfo(path=file_path)
    
    try:
        # Find root node (first [node] entry)
        root_match = re.search(
            r'\[node\s+name="([^"]+)"\s+type="([^"]+)"',
            content
        )
        if root_match:
            info.root_name = root_match.group(1)
            info.root_type = root_match.group(2)
        
        # Find attached script on root
        script_match = re.search(
            r'\[node\s+name="[^"]+"\s+type="[^"]+"\].*?script\s*=\s*ExtResource\s*\(\s*"([^"]+)"',
            content,
            re.DOTALL
        )
        if script_match:
            info.attached_script = script_match.group(1)
        else:
            # Try alternate format
            alt_match = re.search(
                r'\[ext_resource\s+type="Script"\s+path="([^"]+)"',
                content
            )
            if alt_match:
                info.attached_script = alt_match.group(1)
        
        # Count instanced scenes
        info.instance_count = len(re.findall(r'instance\s*=\s*ExtResource', content))
        
    except Exception:
        pass  # Silent fail
    
    return info


async def gather_project_context(
    max_scripts: int = 50,
    max_scenes: int = 30,
    max_resources: int = 20,
) -> ProjectContext | None:
    """Gather comprehensive context from the current Godot project.
    
    Prioritizes scene/node hierarchies and script dependencies.
    
    Args:
        max_scripts: Maximum number of scripts to analyze
        max_scenes: Maximum number of scenes to analyze  
        max_resources: Maximum number of resource paths to include
        
    Returns:
        ProjectContext with project information, or None if no project connected
    """
    project_path_str = get_project_path()
    if not project_path_str:
        return None
    
    project_path = Path(project_path_str)
    if not project_path.exists():
        return None
    
    # Parse project.godot for basic info
    project_info = _parse_project_godot(project_path)
    
    context = ProjectContext(
        project_path=project_path_str,
        project_name=project_info.get("project_name", ""),
        main_scene=project_info.get("main_scene"),
        autoloads=project_info.get("autoloads", {}),
    )
    
    # Gather directories (excluding hidden and imports)
    try:
        for item in sorted(project_path.iterdir()):
            if item.is_dir() and not item.name.startswith('.') and item.name != '.godot':
                context.directories.append(item.name)
    except Exception:
        pass
    
    # Gather and parse scripts (prioritized)
    scripts_found = list(project_path.rglob("*.gd"))[:max_scripts]
    class_to_script: dict[str, str] = {}
    
    for script_path in scripts_found:
        try:
            content = script_path.read_text(encoding="utf-8")
            rel_path = f"res://{script_path.relative_to(project_path)}"
            script_info = _parse_gdscript(content, rel_path)
            context.scripts.append(script_info)
            
            # Build class hierarchy
            if script_info.class_name:
                class_to_script[script_info.class_name] = rel_path
            
            if script_info.extends and script_info.class_name:
                base = script_info.extends
                if base not in context.class_hierarchy:
                    context.class_hierarchy[base] = []
                context.class_hierarchy[base].append(script_info.class_name)
                
        except Exception:
            continue
    
    # Gather and parse scenes (prioritized)
    scenes_found = list(project_path.rglob("*.tscn"))[:max_scenes]
    
    for scene_path in scenes_found:
        try:
            content = scene_path.read_text(encoding="utf-8")
            rel_path = f"res://{scene_path.relative_to(project_path)}"
            scene_info = _parse_scene_file(content, rel_path)
            context.scenes.append(scene_info)
        except Exception:
            continue
    
    # Gather other resources (lower priority)
    resource_extensions = ['*.tres', '*.res', '*.png', '*.wav', '*.ogg']
    resources_found = []
    for ext in resource_extensions:
        resources_found.extend(project_path.rglob(ext))
        if len(resources_found) >= max_resources:
            break
    
    for res_path in resources_found[:max_resources]:
        try:
            rel_path = f"res://{res_path.relative_to(project_path)}"
            context.resources.append(rel_path)
        except Exception:
            continue
    
    return context


def format_context_for_agent(ctx: ProjectContext) -> str:
    """Format project context as a system prompt section.
    
    Creates a concise but comprehensive summary for agent consumption.
    Prioritizes scene/node hierarchies and script dependencies.
    """
    lines = [
        "## Current Project Context\n",
        f"**Project:** {ctx.project_name or 'Unknown'} (at `{ctx.project_path}`)",
    ]
    
    if ctx.main_scene:
        lines.append(f"**Main Scene:** `{ctx.main_scene}`")
    
    # Autoloads (important for understanding globals)
    if ctx.autoloads:
        lines.append("\n### Autoloads (Singletons)")
        for name, path in ctx.autoloads.items():
            lines.append(f"- **{name}**: `{path}`")
    
    # Scene hierarchy (prioritized)
    if ctx.scenes:
        lines.append(f"\n### Scenes ({len(ctx.scenes)} total)")
        for scene in ctx.scenes[:15]:  # Limit to 15 for context window
            root_info = f"{scene.root_type}" if scene.root_type else "?"
            script_info = f" → `{scene.attached_script}`" if scene.attached_script else ""
            instances = f" ({scene.instance_count} instances)" if scene.instance_count > 0 else ""
            lines.append(f"- `{scene.path}`: {root_info}{script_info}{instances}")
    
    # Script dependencies and class hierarchy (prioritized)
    if ctx.scripts:
        lines.append(f"\n### Scripts ({len(ctx.scripts)} total)")
        
        # Show scripts with class names first
        named_scripts = [s for s in ctx.scripts if s.class_name]
        for script in named_scripts[:10]:
            extends_info = f" extends {script.extends}" if script.extends else ""
            lines.append(f"- **{script.class_name}** (`{script.path}`){extends_info}")
        
        # Show class hierarchy
        if ctx.class_hierarchy:
            lines.append("\n### Class Hierarchy")
            for base, derived in sorted(ctx.class_hierarchy.items()):
                derived_str = ", ".join(derived[:5])
                if len(derived) > 5:
                    derived_str += f", +{len(derived) - 5} more"
                lines.append(f"- **{base}** ← {derived_str}")
    
    # Directory structure
    if ctx.directories:
        lines.append(f"\n### Project Structure")
        lines.append("Directories: " + ", ".join(f"`{d}/`" for d in ctx.directories[:10]))
    
    # Resource summary (brief)
    if ctx.resources:
        lines.append(f"\n### Resources: {len(ctx.resources)} files")
    
    return "\n".join(lines)


# Cache for project context
_cached_context: ProjectContext | None = None
_context_cache_valid: bool = False


def invalidate_context_cache() -> None:
    """Invalidate the cached project context.
    
    Should be called when:
    - Project changes (scene_changed, script_changed events)
    - Godot disconnects
    """
    global _context_cache_valid
    _context_cache_valid = False


async def get_cached_context(force_refresh: bool = False) -> ProjectContext | None:
    """Get project context, using cache when valid.
    
    Args:
        force_refresh: If True, always re-gather context
        
    Returns:
        Cached or freshly gathered ProjectContext
    """
    global _cached_context, _context_cache_valid
    
    if force_refresh or not _context_cache_valid or _cached_context is None:
        _cached_context = await gather_project_context()
        _context_cache_valid = True
    
    return _cached_context
