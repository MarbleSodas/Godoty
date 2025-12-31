"""Godot Documentation Loader.

Fetches and parses Godot's XML class reference documentation from GitHub.
Converts to structured Document objects for vector indexing.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import httpx

if TYPE_CHECKING:
    from agno.knowledge.document import Document

logger = logging.getLogger(__name__)

# GitHub raw content base URL
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/godotengine/godot"

# Core classes to prioritize (these are most commonly needed)
PRIORITY_CLASSES = [
    "Node", "Node2D", "Node3D", "Control",
    "CharacterBody2D", "CharacterBody3D", "RigidBody2D", "RigidBody3D",
    "Sprite2D", "Sprite3D", "AnimatedSprite2D", "AnimatedSprite3D",
    "Camera2D", "Camera3D",
    "CollisionShape2D", "CollisionShape3D",
    "Area2D", "Area3D",
    "TileMap", "TileMapLayer",
    "AnimationPlayer", "AnimationTree",
    "AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D",
    "Timer", "CanvasLayer", "ParallaxBackground",
    "Label", "Button", "TextEdit", "LineEdit",
    "PackedScene", "Resource", "Script",
    "Vector2", "Vector3", "Transform2D", "Transform3D",
    "Color", "Rect2", "AABB",
    "Array", "Dictionary", "String",
    "Input", "InputEvent", "InputEventKey", "InputEventMouseButton",
    "SceneTree", "Viewport",
    "Signal", "Callable",
]


# GDScript language reference classes (core language features)
GDSCRIPT_REFERENCE_CLASSES = [
    # Built-in functions and global scope
    "@GDScript",      # Built-in functions (preload, load, range, print, etc.)
    "@GlobalScope",   # Global enums, constants, and singletons
    
    # Primitive types
    "bool", "int", "float", "String", "StringName",
    
    # Container types
    "Array", "Dictionary",
    "PackedByteArray", "PackedInt32Array", "PackedInt64Array",
    "PackedFloat32Array", "PackedFloat64Array",
    "PackedStringArray", "PackedVector2Array", "PackedVector3Array",
    "PackedColorArray",
    
    # Math types (essential for game dev)
    "Vector2", "Vector2i", "Vector3", "Vector3i", "Vector4", "Vector4i",
    "Rect2", "Rect2i", "AABB",
    "Transform2D", "Transform3D", "Basis", "Quaternion",
    "Projection", "Plane",
    "Color",
    
    # Core utilities
    "Callable", "Signal", "RID", "NodePath",
    "Object", "RefCounted", "Resource", "Node",
    
    # Commonly used resources
    "Texture2D", "ImageTexture", "AtlasTexture",
    "AudioStream", "AudioStreamWAV", "AudioStreamMP3",
    "Font", "FontFile", "Theme",
    "Material", "ShaderMaterial", "StandardMaterial3D",
    "Mesh", "ArrayMesh", "PrimitiveMesh",
    
    # Tweening and animation
    "Tween", "PropertyTweener", "IntervalTweener",
]


# Curated tutorials with version placeholders - {version} is replaced at runtime
TUTORIAL_TEMPLATES = [
    {
        "name": "GDScript Style Guide",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/scripting/gdscript/gdscript_styleguide.html",
        "type": "best_practices",
        "description": "Official style guide for GDScript conventions",
    },
    {
        "name": "GDScript Reference",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/scripting/gdscript/gdscript_basics.html",
        "type": "reference",
        "description": "GDScript language basics and syntax",
    },
    {
        "name": "GDScript Exports",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/scripting/gdscript/gdscript_exports.html",
        "type": "reference",
        "description": "@export annotations for inspector properties",
    },
    {
        "name": "Signals",
        "url_template": "https://docs.godotengine.org/en/{version}/getting_started/step_by_step/signals.html",
        "type": "tutorial",
        "description": "Using signals for decoupled communication",
    },
    {
        "name": "Using CharacterBody2D",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/physics/using_character_body_2d.html",
        "type": "tutorial",
        "description": "2D character movement with CharacterBody2D",
    },
    {
        "name": "Custom Resources",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/scripting/resources.html",
        "type": "patterns",
        "description": "Using Resource for data containers",
    },
    {
        "name": "Singletons (Autoload)",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/scripting/singletons_autoload.html",
        "type": "patterns",
        "description": "Global managers with Autoload",
    },
    {
        "name": "Running Code in the Editor",
        "url_template": "https://docs.godotengine.org/en/{version}/tutorials/plugins/running_code_in_the_editor.html",
        "type": "patterns",
        "description": "@tool annotation and editor plugins",
    },
]


def get_tutorials_for_version(version: str) -> list[dict]:
    """Generate tutorial list with URLs adapted for the given version."""
    return [
        {
            "name": tutorial["name"],
            "url": tutorial["url_template"].format(version=version),
            "type": tutorial["type"],
            "description": tutorial["description"],
        }
        for tutorial in TUTORIAL_TEMPLATES
    ]


# Legacy dict kept for backwards compatibility
COMMUNITY_TUTORIALS: dict[str, list[dict]] = {
    "4.3": get_tutorials_for_version("4.3"),
    "4.2": get_tutorials_for_version("4.2"),
}


class GodotDocsLoader:
    """Fetches and parses Godot documentation from GitHub.
    
    Downloads XML class reference files and converts them to Document
    objects suitable for vector indexing.
    """
    
    def __init__(
        self,
        version: str = "4.5",
        cache_dir: Path | None = None,
    ):
        """Initialize the documentation loader.
        
        Args:
            version: Godot version to fetch docs for (e.g., "4.3", "4.2")
            cache_dir: Directory to cache downloaded XML files
        """
        self.version = version
        self.cache_dir = cache_dir or (Path.home() / ".godoty" / "knowledge" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine GitHub tag
        self._tag = f"{version}-stable"
    
    def _get_class_list_url(self) -> str:
        """Get URL for the doc/classes directory listing."""
        # GitHub API for directory listing
        return f"https://api.github.com/repos/godotengine/godot/contents/doc/classes?ref={self._tag}"
    
    def _get_class_url(self, class_name: str) -> str:
        """Get raw URL for a specific class XML file."""
        return f"{GITHUB_RAW_BASE}/{self._tag}/doc/classes/{class_name}.xml"
    
    async def _fetch_class_list(self) -> list[str]:
        """Fetch list of available class documentation files.
        
        Returns:
            List of class names (without .xml extension)
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    self._get_class_list_url(),
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                response.raise_for_status()
                
                files = response.json()
                class_names = []
                
                for file_info in files:
                    name = file_info.get("name", "")
                    if name.endswith(".xml"):
                        class_names.append(name[:-4])
                
                logger.info(f"Found {len(class_names)} classes in Godot {self.version} docs")
                return class_names
                
            except Exception as e:
                logger.error(f"Failed to fetch class list: {e}")
                # Fall back to priority classes
                return PRIORITY_CLASSES
    
    async def _fetch_class_xml(self, class_name: str) -> str | None:
        """Fetch XML content for a specific class.

        Args:
            class_name: Name of the class (e.g., "CharacterBody2D")

        Returns:
            XML content as string, or None if fetch failed
        """
        import aiofiles

        # Check cache first
        cache_path = self.cache_dir / f"{class_name}.xml"
        if cache_path.exists():
            async with aiofiles.open(cache_path, encoding="utf-8") as f:
                return await f.read()

        # Fetch from GitHub
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                url = self._get_class_url(class_name)
                response = await client.get(url)
                response.raise_for_status()

                content = response.text

                # Cache for future use
                async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
                    await f.write(content)

                return content

            except Exception as e:
                logger.debug(f"Failed to fetch {class_name}: {e}")
                return None
    
    def _parse_class_xml(self, class_name: str, xml_content: str) -> list[dict]:
        """Parse XML class documentation into chunks.
        
        Each class is split into multiple chunks:
        - Class description
        - Methods (grouped)
        - Properties
        - Signals
        
        Args:
            class_name: Name of the class
            xml_content: Raw XML content
            
        Returns:
            List of document chunks with content and metadata
        """
        chunks = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Class description
            brief = root.find("brief_description")
            description = root.find("description")
            
            class_desc = f"# {class_name}\n\n"
            if brief is not None and brief.text:
                class_desc += f"{brief.text.strip()}\n\n"
            if description is not None and description.text:
                class_desc += f"## Description\n{description.text.strip()}\n"
            
            # Get inheritance
            inherits = root.get("inherits", "")
            if inherits:
                class_desc = f"**Inherits:** {inherits}\n\n" + class_desc
            
            chunks.append({
                "content": class_desc,
                "name": f"{class_name} - Overview",
                "metadata": {
                    "class": class_name,
                    "type": "class_description",
                    "version": self.version,
                },
            })
            
            # Methods
            methods = root.find("methods")
            if methods is not None:
                method_docs = []
                for method in methods.findall("method"):
                    method_name = method.get("name", "")
                    if not method_name or method_name.startswith("_"):
                        continue
                    
                    # Build signature
                    return_elem = method.find("return")
                    return_type = return_elem.get("type", "void") if return_elem is not None else "void"
                    
                    params = []
                    for param in method.findall("param"):
                        param_name = param.get("name", "")
                        param_type = param.get("type", "Variant")
                        default = param.get("default", "")
                        if default:
                            params.append(f"{param_name}: {param_type} = {default}")
                        else:
                            params.append(f"{param_name}: {param_type}")
                    
                    signature = f"{method_name}({', '.join(params)}) -> {return_type}"
                    
                    desc = method.find("description")
                    desc_text = desc.text.strip() if desc is not None and desc.text else ""
                    
                    method_docs.append(f"### {method_name}\n```gdscript\n{signature}\n```\n{desc_text}")
                
                if method_docs:
                    # Split into chunks if too many methods
                    chunk_size = 10
                    for i in range(0, len(method_docs), chunk_size):
                        chunk_methods = method_docs[i:i + chunk_size]
                        chunks.append({
                            "content": f"# {class_name} Methods\n\n" + "\n\n".join(chunk_methods),
                            "name": f"{class_name} - Methods ({i // chunk_size + 1})",
                            "metadata": {
                                "class": class_name,
                                "type": "methods",
                                "version": self.version,
                            },
                        })
            
            # Properties
            members = root.find("members")
            if members is not None:
                prop_docs = []
                for member in members.findall("member"):
                    prop_name = member.get("name", "")
                    prop_type = member.get("type", "Variant")
                    default = member.get("default", "")
                    
                    prop_text = f"**{prop_name}**: `{prop_type}`"
                    if default:
                        prop_text += f" = `{default}`"
                    if member.text:
                        prop_text += f"\n{member.text.strip()}"
                    
                    prop_docs.append(prop_text)
                
                if prop_docs:
                    chunks.append({
                        "content": f"# {class_name} Properties\n\n" + "\n\n".join(prop_docs),
                        "name": f"{class_name} - Properties",
                        "metadata": {
                            "class": class_name,
                            "type": "properties",
                            "version": self.version,
                        },
                    })
            
            # Signals
            signals = root.find("signals")
            if signals is not None:
                signal_docs = []
                for signal in signals.findall("signal"):
                    signal_name = signal.get("name", "")
                    
                    params = []
                    for param in signal.findall("param"):
                        param_name = param.get("name", "")
                        param_type = param.get("type", "Variant")
                        params.append(f"{param_name}: {param_type}")
                    
                    signal_text = f"**{signal_name}**({', '.join(params)})"
                    
                    desc = signal.find("description")
                    if desc is not None and desc.text:
                        signal_text += f"\n{desc.text.strip()}"
                    
                    signal_docs.append(signal_text)
                
                if signal_docs:
                    chunks.append({
                        "content": f"# {class_name} Signals\n\n" + "\n\n".join(signal_docs),
                        "name": f"{class_name} - Signals",
                        "metadata": {
                            "class": class_name,
                            "type": "signals",
                            "version": self.version,
                        },
                    })
            
        except ET.ParseError as e:
            logger.warning(f"Failed to parse XML for {class_name}: {e}")
        
        return chunks
    
    async def load_documents(
        self,
        classes: list[str] | None = None,
        max_classes: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list:
        """Load and parse Godot documentation into Document objects.
        
        Args:
            classes: Specific classes to load (None = load priority classes)
            max_classes: Maximum number of classes to load (for testing)
            
        Returns:
            List of Agno Document objects ready for indexing
        """
        from agno.knowledge.document import Document

        # Determine which classes to fetch
        if classes is None:
            # Start with priority classes, optionally expand
            classes = PRIORITY_CLASSES.copy()

        if max_classes:
            classes = classes[:max_classes]

        # Use semaphore to limit concurrent requests
        concurrency = 5
        semaphore = asyncio.Semaphore(concurrency)
        logger.info(f"Loading documentation for {len(classes)} Godot classes with concurrency={concurrency}")

        # Process classes in parallel batches
        async def fetch_and_parse(class_name: str, index: int) -> list[Document]:
            async with semaphore:
                # Fetch XML
                xml_content = await self._fetch_class_xml(class_name)

                # Update progress
                if progress_callback:
                    try:
                        progress_callback(index + 1, len(classes))
                    except Exception as e:
                        logger.warning(f"Progress callback failed: {e}")

                # Parse and create documents
                if xml_content:
                    chunks = self._parse_class_xml(class_name, xml_content)
                    docs = []
                    for chunk in chunks:
                        doc = Document(
                            content=chunk["content"],
                            name=chunk["name"],
                            meta_data=chunk["metadata"],
                        )
                        docs.append(doc)
                    return docs
                return []

        # Create tasks for all classes
        tasks = [fetch_and_parse(class_name, i) for i, class_name in enumerate(classes)]

        # Process in parallel, collecting results as they complete
        documents = []
        for completed in asyncio.as_completed(tasks):
            try:
                docs = await completed
                documents.extend(docs)
            except Exception as e:
                logger.warning(f"Failed to load class documentation: {e}")

        logger.info(f"Loaded {len(documents)} document chunks from Godot {self.version} docs")
        return documents

