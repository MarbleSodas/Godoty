"""Project-specific knowledge base with hash-based invalidation.

Indexes all project files (.gd, .tscn) for semantic search.
Uses content hashing to detect changes and re-index only when needed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agno.knowledge.document import Document
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType

from .godot_knowledge import KNOWLEDGE_DIR, _get_embedder

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

PROJECT_KNOWLEDGE_DIR = KNOWLEDGE_DIR / "projects"


@dataclass
class FileManifest:
    project_path: str
    files: dict[str, str] = field(default_factory=dict)
    indexed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "files": self.files,
            "indexed_at": self.indexed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileManifest":
        return cls(
            project_path=data.get("project_path", ""),
            files=data.get("files", {}),
            indexed_at=data.get("indexed_at", ""),
        )


class ProjectKnowledge:
    """Knowledge base for a specific Godot project with hash-based invalidation."""

    SCRIPT_PATTERNS = ["**/*.gd"]
    SCENE_PATTERNS = ["**/*.tscn"]
    SKIP_DIRS = {".godot", ".git", "addons", ".import"}

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.project_hash = self._hash_path(str(self.project_path))

        PROJECT_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

        self.table_name = f"project_{self.project_hash}"
        self.manifest_path = PROJECT_KNOWLEDGE_DIR / f"{self.table_name}_manifest.json"

        embedder = _get_embedder()
        self.vector_db = LanceDb(
            table_name=self.table_name,
            uri=str(PROJECT_KNOWLEDGE_DIR),
            embedder=embedder,
            search_type=SearchType.hybrid,
        )

        self.knowledge = Knowledge(vector_db=self.vector_db)

        self._manifest: FileManifest | None = None
        self._indexing = False

        logger.info(f"ProjectKnowledge initialized for: {self.project_path}")

    @staticmethod
    def _hash_path(path: str) -> str:
        return hashlib.md5(path.encode()).hexdigest()[:12]

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _load_manifest(self) -> FileManifest:
        import aiofiles

        if self._manifest:
            return self._manifest

        if self.manifest_path.exists():
            try:
                async with aiofiles.open(self.manifest_path, encoding="utf-8") as f:
                    data = json.loads(await f.read())
                self._manifest = FileManifest.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load manifest: {e}")
                self._manifest = FileManifest(project_path=str(self.project_path))
        else:
            self._manifest = FileManifest(project_path=str(self.project_path))

        return self._manifest

    async def _save_manifest(self, manifest: FileManifest) -> None:
        import aiofiles

        manifest.indexed_at = datetime.now().isoformat()
        async with aiofiles.open(self.manifest_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(manifest.to_dict(), indent=2))
        self._manifest = manifest

    def _should_skip(self, path: Path) -> bool:
        for part in path.parts:
            if part in self.SKIP_DIRS:
                return True
        return False

    async def _get_changed_files(self) -> tuple[list[Path], list[str], list[Path]]:
        import aiofiles

        manifest = await self._load_manifest()
        current_files: dict[str, tuple[Path, str]] = {}

        for pattern in self.SCRIPT_PATTERNS + self.SCENE_PATTERNS:
            for file_path in self.project_path.glob(pattern):
                if self._should_skip(file_path):
                    continue

                try:
                    async with aiofiles.open(file_path, encoding="utf-8") as f:
                        content = await f.read()
                    rel_path = str(file_path.relative_to(self.project_path))
                    content_hash = self._hash_content(content)
                    current_files[rel_path] = (file_path, content_hash)
                except Exception:
                    continue

        new_files: list[Path] = []
        modified_files: list[Path] = []
        deleted_paths: list[str] = []

        for rel_path, (full_path, current_hash) in current_files.items():
            old_hash = manifest.files.get(rel_path)
            if old_hash is None:
                new_files.append(full_path)
            elif old_hash != current_hash:
                modified_files.append(full_path)

        for rel_path in manifest.files:
            if rel_path not in current_files:
                deleted_paths.append(rel_path)

        return new_files, deleted_paths, modified_files

    async def index_project(self, force: bool = False) -> dict[str, Any]:
        import aiofiles

        if self._indexing:
            logger.warning("Indexing already in progress")
            return {"status": "already_indexing"}

        self._indexing = True
        stats = {"new": 0, "modified": 0, "deleted": 0, "unchanged": 0}

        try:
            manifest = await self._load_manifest()

            if force:
                await self._clear_index()
                manifest = FileManifest(project_path=str(self.project_path))
                files_to_index = list(self._get_all_files())
                files_to_delete: list[str] = []
            else:
                new_files, deleted_paths, modified_files = await self._get_changed_files()
                files_to_index = new_files + modified_files
                files_to_delete = deleted_paths
                stats["new"] = len(new_files)
                stats["modified"] = len(modified_files)
                stats["deleted"] = len(deleted_paths)

            for rel_path in files_to_delete:
                manifest.files.pop(rel_path, None)

            if files_to_index:
                documents = []
                new_hashes: dict[str, str] = {}

                for file_path in files_to_index:
                    try:
                        doc = await self._create_document(file_path)
                        if doc:
                            documents.append(doc)
                            rel_path = str(file_path.relative_to(self.project_path))
                            async with aiofiles.open(file_path, encoding="utf-8") as f:
                                content = await f.read()
                            new_hashes[rel_path] = self._hash_content(content)
                    except Exception as e:
                        logger.warning(f"Failed to index {file_path}: {e}")

                if documents:
                    batch_hash = hashlib.md5(
                        f"{self.project_hash}_{datetime.now().isoformat()}".encode()
                    ).hexdigest()

                    batch_size = 10
                    for i in range(0, len(documents), batch_size):
                        batch = documents[i : i + batch_size]
                        await self.vector_db.async_insert(f"{batch_hash}_{i}", batch)

                    manifest.files.update(new_hashes)

                    if force:
                        stats["new"] = len(documents)

            total_files = len(manifest.files)
            stats["unchanged"] = total_files - stats["new"] - stats["modified"]

            await self._save_manifest(manifest)

            logger.info(
                f"Project indexed: {stats['new']} new, {stats['modified']} modified, "
                f"{stats['deleted']} deleted, {stats['unchanged']} unchanged"
            )

            return stats

        except Exception as e:
            logger.error(f"Project indexing failed: {e}")
            return {"error": str(e)}
        finally:
            self._indexing = False

    def _get_all_files(self) -> list[Path]:
        files = []
        for pattern in self.SCRIPT_PATTERNS + self.SCENE_PATTERNS:
            for file_path in self.project_path.glob(pattern):
                if not self._should_skip(file_path):
                    files.append(file_path)
        return files

    async def _clear_index(self) -> None:
        import shutil

        table_dir = PROJECT_KNOWLEDGE_DIR / f"{self.table_name}.lance"
        if table_dir.exists():
            try:
                shutil.rmtree(table_dir)
            except Exception as e:
                logger.warning(f"Failed to clear index: {e}")

    async def _create_document(self, file_path: Path) -> Document | None:
        try:
            content = file_path.read_text(encoding="utf-8")
            rel_path = str(file_path.relative_to(self.project_path))
            suffix = file_path.suffix.lower()

            if suffix == ".gd":
                return self._create_script_document(rel_path, content)
            elif suffix == ".tscn":
                return self._create_scene_document(rel_path, content)
            else:
                return None

        except Exception as e:
            logger.warning(f"Failed to create document for {file_path}: {e}")
            return None

    def _create_script_document(self, path: str, content: str) -> Document:
        class_name = None
        extends = None
        signals: list[str] = []
        exports: list[str] = []
        functions: list[str] = []

        class_match = re.search(r"^class_name\s+(\w+)", content, re.MULTILINE)
        if class_match:
            class_name = class_match.group(1)

        extends_match = re.search(r"^extends\s+(\w+)", content, re.MULTILINE)
        if extends_match:
            extends = extends_match.group(1)

        for sig_match in re.finditer(r"^signal\s+(\w+)", content, re.MULTILINE):
            signals.append(sig_match.group(1))

        for exp_match in re.finditer(r"^@export[^\n]*var\s+(\w+)", content, re.MULTILINE):
            exports.append(exp_match.group(1))

        for func_match in re.finditer(r"^func\s+(\w+)", content, re.MULTILINE):
            functions.append(func_match.group(1))

        header_parts = [f"# GDScript: {path}"]
        if class_name:
            header_parts.append(f"class_name {class_name}")
        if extends:
            header_parts.append(f"extends {extends}")
        if signals:
            header_parts.append(f"Signals: {', '.join(signals[:10])}")
        if exports:
            header_parts.append(f"Exports: {', '.join(exports[:10])}")
        if functions:
            header_parts.append(f"Functions: {', '.join(functions[:15])}")

        header = "\n".join(header_parts)

        max_content_len = 8000
        if len(content) > max_content_len:
            content = content[:max_content_len] + "\n# ... (truncated)"

        return Document(
            content=f"{header}\n\n{content}",
            name=path,
            meta_data={
                "path": path,
                "type": "script",
                "class_name": class_name,
                "extends": extends,
                "signals": signals[:10],
                "exports": exports[:10],
                "functions": functions[:20],
            },
        )

    def _create_scene_document(self, path: str, content: str) -> Document:
        root_type = None
        root_name = None
        attached_script = None
        node_count = 0

        root_match = re.search(r'\[node\s+name="([^"]+)"\s+type="([^"]+)"', content)
        if root_match:
            root_name = root_match.group(1)
            root_type = root_match.group(2)

        node_count = len(re.findall(r"\[node\s+", content))

        script_match = re.search(r'\[ext_resource\s+type="Script"\s+path="([^"]+)"', content)
        if script_match:
            attached_script = script_match.group(1)

        header_parts = [f"# Scene: {path}"]
        if root_name and root_type:
            header_parts.append(f"Root: {root_name} ({root_type})")
        if attached_script:
            header_parts.append(f"Script: {attached_script}")
        header_parts.append(f"Nodes: {node_count}")

        header = "\n".join(header_parts)

        max_content_len = 4000
        if len(content) > max_content_len:
            content = content[:max_content_len] + "\n# ... (truncated)"

        return Document(
            content=f"{header}\n\n{content}",
            name=path,
            meta_data={
                "path": path,
                "type": "scene",
                "root_type": root_type,
                "root_name": root_name,
                "attached_script": attached_script,
                "node_count": node_count,
            },
        )

    async def search(
        self,
        query: str,
        num_results: int = 5,
        file_type: str | None = None,
    ) -> list[dict]:
        try:
            fetch_limit = num_results * 2 if file_type else num_results

            results = await self.vector_db.async_search(query, limit=fetch_limit)

            if file_type:
                results = [r for r in results if r.meta_data.get("type") == file_type]

            return [
                {
                    "content": doc.content,
                    "name": doc.name,
                    "metadata": doc.meta_data,
                }
                for doc in results[:num_results]
            ]

        except Exception as e:
            logger.error(f"Project search failed: {e}")
            return []

    async def get_file(self, path: str) -> dict | None:
        try:
            results = await self.vector_db.async_search(path, limit=5)

            for doc in results:
                if doc.meta_data.get("path") == path:
                    return {
                        "content": doc.content,
                        "name": doc.name,
                        "metadata": doc.meta_data,
                    }

            return None

        except Exception:
            return None

    async def is_indexed(self) -> bool:
        try:
            count = await self.vector_db.async_get_count()
            return count > 0
        except Exception:
            return False

    @property
    def is_indexing(self) -> bool:
        return self._indexing


_project_knowledge_cache: dict[str, ProjectKnowledge] = {}


def get_project_knowledge(project_path: str) -> ProjectKnowledge:
    resolved = str(Path(project_path).resolve())

    if resolved not in _project_knowledge_cache:
        _project_knowledge_cache[resolved] = ProjectKnowledge(resolved)

    return _project_knowledge_cache[resolved]


def clear_project_knowledge(project_path: str | None = None) -> None:
    if project_path:
        resolved = str(Path(project_path).resolve())
        _project_knowledge_cache.pop(resolved, None)
    else:
        _project_knowledge_cache.clear()
