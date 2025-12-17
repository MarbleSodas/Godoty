"""Tests for scoped file tools."""

import asyncio
import tempfile
import pytest
from pathlib import Path


class TestPathValidation:
    """Tests for path validation in scoped file tools."""

    def test_validate_path_in_project_rejects_no_project(self):
        """Test that validation fails when no project is connected."""
        from app.agents.tools import _validate_path_in_project, set_project_path
        
        set_project_path(None)
        
        with pytest.raises(ValueError, match="No Godot project connected"):
            _validate_path_in_project("test.gd")

    def test_validate_path_in_project_accepts_valid_path(self):
        """Test that validation accepts valid paths within project."""
        from app.agents.tools import _validate_path_in_project, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            # Create a test file
            test_file = Path(tmpdir) / "scripts" / "test.gd"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.touch()
            
            # Validate should succeed
            result = _validate_path_in_project("scripts/test.gd")
            assert result == test_file.resolve()
            
            set_project_path(None)

    def test_validate_path_in_project_rejects_traversal(self):
        """Test that validation rejects path traversal attempts."""
        from app.agents.tools import _validate_path_in_project, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            # Various traversal attempts should fail
            traversal_paths = [
                "../etc/passwd",
                "scripts/../../etc/passwd",
                "/etc/passwd",
                "scripts/../../../home/user",
            ]
            
            for path in traversal_paths:
                with pytest.raises(ValueError, match="escapes project directory"):
                    _validate_path_in_project(path)
            
            set_project_path(None)


class TestScopedFileTools:
    """Tests for scoped file tool functions."""

    def test_list_project_files(self):
        """Test listing files in a project directory."""
        from app.agents.tools import list_project_files, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            # Create some test files
            (Path(tmpdir) / "test.gd").touch()
            (Path(tmpdir) / "test.tscn").touch()
            (Path(tmpdir) / "scripts").mkdir()
            (Path(tmpdir) / "scripts" / "player.gd").touch()
            
            # List root directory
            result = asyncio.run(list_project_files())
            assert len(result) == 3  # test.gd, test.tscn, scripts/
            
            # List with pattern
            result = asyncio.run(list_project_files(pattern="*.gd"))
            assert len(result) == 1
            assert result[0]["name"] == "test.gd"
            
            set_project_path(None)

    def test_read_file_success(self):
        """Test reading a file from the project."""
        from app.agents.tools import read_file, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            # Create a test file with content
            test_file = Path(tmpdir) / "test.gd"
            test_file.write_text("extends Node\n\nfunc _ready():\n    pass\n")
            
            result = asyncio.run(read_file("test.gd"))
            assert "extends Node" in result
            assert "func _ready" in result
            
            set_project_path(None)

    def test_read_file_rejects_traversal(self):
        """Test that read_file rejects path traversal."""
        from app.agents.tools import read_file, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            result = asyncio.run(read_file("../etc/passwd"))
            assert "Error:" in result
            assert "escapes project directory" in result
            
            set_project_path(None)

    def test_file_exists(self):
        """Test checking file existence."""
        from app.agents.tools import file_exists, set_project_path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            set_project_path(tmpdir)
            
            # Create a test file
            (Path(tmpdir) / "exists.gd").touch()
            
            assert asyncio.run(file_exists("exists.gd")) is True
            assert asyncio.run(file_exists("not_exists.gd")) is False
            
            # Traversal should return False (not raise)
            assert asyncio.run(file_exists("../etc/passwd")) is False
            
            set_project_path(None)

    def test_tools_exported(self):
        """Test that all scoped file tools are exported."""
        from app.agents.tools import (
            list_project_files,
            read_file,
            write_file,
            delete_file,
            file_exists,
            set_project_path,
            get_project_path,
        )
        
        assert callable(list_project_files)
        assert callable(read_file)
        assert callable(write_file)
        assert callable(delete_file)
        assert callable(file_exists)
        assert callable(set_project_path)
        assert callable(get_project_path)
