"""
Simplified Godot XML Documentation Parser and SQLite Database Builder

Downloads Godot documentation XML files from official GitHub repository,
parses them, and populates a lightweight SQLite database with FTS5 search.
"""

import os
import sys
import sqlite3
import urllib.request
import json
import ssl
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Callable, Dict, List, Optional

# Add backend to path for user_data import when running as script
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from user_data import get_docs_db_path, get_docs_rebuild_db_path

# Database configuration - uses user data directory (~/.godoty/)
DEFAULT_DB_PATH = get_docs_db_path()
TEMP_DB_PATH = get_docs_rebuild_db_path()
DEFAULT_GODOT_VERSION = "4.5.1-stable"
GITHUB_API_BASE = "https://api.github.com/repos/godotengine/godot"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/godotengine/godot"


class DocumentationBuilder:
    """Builds Godot documentation database from official XML files."""

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH)):
        self.db_path = os.path.abspath(db_path)
        self.conn = None
        self.stats = {
            "classes": 0,
            "methods": 0,
            "properties": 0,
            "signals": 0
        }

        # Create SSL context for HTTPS requests
        # This handles certificate verification issues on macOS
        try:
            import certifi
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            # Fallback to default context if certifi is not installed
            self.ssl_context = ssl.create_default_context()

    def build(self, godot_version: str = DEFAULT_GODOT_VERSION, force: bool = False,
              progress_callback: Optional[Callable[[str, int, str, int, int], None]] = None):
        """Build the documentation database.
        
        Args:
            godot_version: Godot version to build docs for
            force: Force rebuild even if database exists
            progress_callback: Optional callback(stage, progress, message, files_processed, files_total)
        """
        def emit_progress(stage: str, progress: int, message: str, processed: int = 0, total: int = 0):
            """Helper to emit progress updates."""
            if progress_callback:
                progress_callback(stage, progress, message, processed, total)
            print(f"[{progress}%] {message}")

        # Check if database exists
        if os.path.exists(self.db_path) and not force:
            print(f"Database already exists at {self.db_path}")
            print("Use --force to rebuild")
            return

        emit_progress("starting", 0, f"Building Godot {godot_version} documentation...")

        try:
            # Initialize database (atomic operation - build to temp first)
            emit_progress("initializing", 2, "Initializing database...")
            self._init_database_atomic()

            # Get list of XML files from GitHub
            emit_progress("fetching", 5, "Fetching file list from GitHub...")
            xml_files = self._get_xml_file_list(godot_version)
            total = len(xml_files)
            emit_progress("fetching", 8, f"Found {total} documentation files", 0, total)

            # Download and parse each XML file
            for idx, file_info in enumerate(xml_files, 1):
                filename = file_info['name']
                # Calculate progress: files take 5% to 90% of the process
                file_progress = 10 + int((idx / total) * 80)
                
                try:
                    # Download XML content
                    emit_progress("downloading", file_progress, f"Downloading {filename}...", idx, total)
                    xml_content = self._download_file(file_info['download_url'])

                    # Parse and insert into database
                    self._parse_and_insert_xml(xml_content, filename)

                except Exception as e:
                    print(f"  Warning: Failed to process {filename}: {e}")
                    continue

            # Store metadata
            emit_progress("finalizing", 92, "Saving metadata...")
            self._save_metadata(godot_version)

            # Commit and close
            emit_progress("finalizing", 95, "Committing changes...")
            self.conn.commit()
            self.conn.close()

            # Atomic move to final location
            emit_progress("finalizing", 98, "Finalizing database...")
            self._finalize_build()

            # Print summary
            total_items = sum(self.stats.values())
            emit_progress("completed", 100, f"Complete! {total_items} items indexed", total, total)
            
            print("\n" + "="*50)
            print("Build completed successfully!")
            print(f"Database: {self.db_path}")
            print(f"Classes: {self.stats['classes']}")
            print(f"Methods: {self.stats['methods']}")
            print(f"Properties: {self.stats['properties']}")
            print(f"Signals: {self.stats['signals']}")
            print(f"Total items: {total_items}")
            print("="*50)

        except Exception as e:
            print(f"\nError building documentation database: {e}")
            # Clean up any partial files on error
            self._cleanup_on_error()
            if self.conn:
                self.conn.close()
            raise

    def _init_database_atomic(self):
        """Initialize temporary database with FTS5 schema for atomic operations."""
        # Remove temporary database if it exists
        if os.path.exists(TEMP_DB_PATH):
            os.remove(TEMP_DB_PATH)

        # Create connection to temporary database
        self.conn = sqlite3.connect(TEMP_DB_PATH)
        cursor = self.conn.cursor()

        # Create FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE godot_docs USING fts5(
                class_name UNINDEXED,
                item_name,
                item_type UNINDEXED,
                brief_description,
                full_description,
                signature,
                return_type UNINDEXED,
                inherits UNINDEXED,
                tokenize='porter unicode61'
            )
        """)

        # Create metadata table
        cursor.execute("""
            CREATE TABLE docs_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        self.conn.commit()
        print("Temporary database initialized with FTS5 schema")

    def _finalize_build(self):
        """Atomically move temporary database to final location."""
        if TEMP_DB_PATH.exists():
            # Remove old database if it exists
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
            # Atomic rename
            TEMP_DB_PATH.rename(self.db_path)
            print(f"Database atomically moved to {self.db_path}")

    def _cleanup_on_error(self):
        """Clean up temporary files on build error."""
        if TEMP_DB_PATH.exists():
            try:
                os.remove(TEMP_DB_PATH)
                print("Cleaned up temporary database file")
            except Exception as e:
                print(f"Warning: Failed to clean up temporary file: {e}")

    def _init_database(self):
        """Initialize database with FTS5 schema."""
        # Remove existing database if it exists
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

        # Create connection
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

        # Create FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE godot_docs USING fts5(
                class_name UNINDEXED,
                item_name,
                item_type UNINDEXED,
                brief_description,
                full_description,
                signature,
                return_type UNINDEXED,
                inherits UNINDEXED,
                tokenize='porter unicode61'
            )
        """)

        # Create metadata table
        cursor.execute("""
            CREATE TABLE docs_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        self.conn.commit()
        print("Database initialized with FTS5 schema")

    def _get_xml_file_list(self, version: str) -> List[Dict]:
        """Get list of XML files from GitHub API."""
        url = f"{GITHUB_API_BASE}/contents/doc/classes?ref={version}"

        try:
            with urllib.request.urlopen(url, context=self.ssl_context) as response:
                files = json.loads(response.read().decode('utf-8'))

            # Filter for .xml files only
            xml_files = [f for f in files if f['name'].endswith('.xml')]
            return xml_files

        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Exception(f"Version '{version}' not found. Try '4.3-stable' or 'master'")
            else:
                raise Exception(f"GitHub API error: {e}")
        except ssl.SSLError as e:
            raise Exception(
                f"SSL certificate verification failed. "
                f"On macOS, run: '/Applications/Python 3.11/Install Certificates.command'. "
                f"Original error: {e}"
            )

    def _download_file(self, url: str) -> str:
        """Download file content from URL."""
        with urllib.request.urlopen(url, context=self.ssl_context) as response:
            return response.read().decode('utf-8')

    def _parse_and_insert_xml(self, xml_content: str, filename: str):
        """Parse XML content and insert into database."""
        try:
            root = ET.fromstring(xml_content)
            class_name = root.get('name')

            if not class_name:
                return

            # Parse class info
            inherits = root.get('inherits', '')
            brief_desc = self._get_elem_text(root.find('brief_description'))
            full_desc = self._get_elem_text(root.find('description'))

            # Insert class entry
            self._insert_doc_entry(
                class_name=class_name,
                item_name=class_name,
                item_type='class',
                brief_description=brief_desc,
                full_description=full_desc,
                signature='',
                return_type='',
                inherits=inherits
            )
            self.stats['classes'] += 1

            # Parse methods
            for method in root.findall('.//method'):
                self._parse_method(class_name, method)

            # Parse properties
            for member in root.findall('.//member'):
                self._parse_property(class_name, member)

            # Parse signals
            for signal in root.findall('.//signal'):
                self._parse_signal(class_name, signal)

        except ET.ParseError as e:
            print(f"  XML parse error in {filename}: {e}")

    def _parse_method(self, class_name: str, method_elem: ET.Element):
        """Parse a method element."""
        method_name = method_elem.get('name')
        if not method_name:
            return

        # Get return type
        return_elem = method_elem.find('return')
        return_type = return_elem.get('type', 'void') if return_elem is not None else 'void'

        # Build signature
        params = []
        for param in method_elem.findall('.//param'):
            param_name = param.get('name', '')
            param_type = param.get('type', 'Variant')
            params.append(f"{param_name}: {param_type}")

        signature = f"func {method_name}({', '.join(params)}) -> {return_type}"

        # Get description
        description = self._get_elem_text(method_elem.find('description'))

        # Insert method entry
        self._insert_doc_entry(
            class_name=class_name,
            item_name=method_name,
            item_type='method',
            brief_description=description[:200] if description else '',  # First 200 chars as brief
            full_description=description,
            signature=signature,
            return_type=return_type,
            inherits=''
        )
        self.stats['methods'] += 1

    def _parse_property(self, class_name: str, member_elem: ET.Element):
        """Parse a property element."""
        prop_name = member_elem.get('name')
        if not prop_name:
            return

        prop_type = member_elem.get('type', 'Variant')
        default_value = member_elem.get('default', '')
        description = self._get_elem_text(member_elem)

        # Build signature
        signature = f"var {prop_name}: {prop_type}"
        if default_value:
            signature += f" = {default_value}"

        # Insert property entry
        self._insert_doc_entry(
            class_name=class_name,
            item_name=prop_name,
            item_type='property',
            brief_description=description[:200] if description else '',
            full_description=description,
            signature=signature,
            return_type=prop_type,
            inherits=''
        )
        self.stats['properties'] += 1

    def _parse_signal(self, class_name: str, signal_elem: ET.Element):
        """Parse a signal element."""
        signal_name = signal_elem.get('name')
        if not signal_name:
            return

        # Build signature
        params = []
        for param in signal_elem.findall('.//param'):
            param_name = param.get('name', '')
            param_type = param.get('type', 'Variant')
            params.append(f"{param_name}: {param_type}")

        signature = f"signal {signal_name}({', '.join(params)})"

        # Get description
        description = self._get_elem_text(signal_elem.find('description'))

        # Insert signal entry
        self._insert_doc_entry(
            class_name=class_name,
            item_name=signal_name,
            item_type='signal',
            brief_description=description[:200] if description else '',
            full_description=description,
            signature=signature,
            return_type='',
            inherits=''
        )
        self.stats['signals'] += 1

    def _insert_doc_entry(self, class_name: str, item_name: str, item_type: str,
                         brief_description: str, full_description: str,
                         signature: str, return_type: str, inherits: str):
        """Insert a documentation entry into the FTS5 table."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO godot_docs (
                class_name, item_name, item_type,
                brief_description, full_description,
                signature, return_type, inherits
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            class_name, item_name, item_type,
            brief_description or '', full_description or '',
            signature or '', return_type or '', inherits or ''
        ))

    def _save_metadata(self, godot_version: str):
        """Save build metadata."""
        cursor = self.conn.cursor()

        metadata = {
            'build_timestamp': datetime.utcnow().isoformat() + 'Z',  # Add Z suffix for UTC
            'godot_version': godot_version,
            'total_classes': str(self.stats['classes']),
            'total_methods': str(self.stats['methods']),
            'total_properties': str(self.stats['properties']),
            'total_signals': str(self.stats['signals'])
        }

        for key, value in metadata.items():
            cursor.execute(
                "INSERT OR REPLACE INTO docs_metadata (key, value) VALUES (?, ?)",
                (key, value)
            )

    @staticmethod
    def _get_elem_text(elem: Optional[ET.Element]) -> str:
        """Safely get text from an XML element."""
        if elem is None:
            return ''
        return (elem.text or '').strip()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build Godot documentation SQLite database"
    )
    parser.add_argument(
        '--db-path',
        default=str(DEFAULT_DB_PATH),
        help=f'Database file path (default: {DEFAULT_DB_PATH})'
    )
    parser.add_argument(
        '--version',
        default=DEFAULT_GODOT_VERSION,
        help=f'Godot version/branch (default: {DEFAULT_GODOT_VERSION})'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force rebuild existing database'
    )

    args = parser.parse_args()

    # Build database
    builder = DocumentationBuilder(args.db_path)
    builder.build(godot_version=args.version, force=args.force)


if __name__ == "__main__":
    main()
