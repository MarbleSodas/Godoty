# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for bundling RAG server with all dependencies

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all necessary data files and hidden imports
datas = []
hiddenimports = []

# FastAPI and dependencies
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('starlette')

# LangChain
hiddenimports += collect_submodules('langchain')
hiddenimports += collect_submodules('langchain_community')
hiddenimports += collect_submodules('langchain_text_splitters')
hiddenimports += collect_submodules('langchain_core')

# ChromaDB
hiddenimports += collect_submodules('chromadb')
datas += collect_data_files('chromadb')

# Sentence Transformers and dependencies
hiddenimports += collect_submodules('sentence_transformers')
datas += collect_data_files('sentence_transformers')
hiddenimports += collect_submodules('transformers')
datas += collect_data_files('transformers')
hiddenimports += collect_submodules('tokenizers')
datas += collect_data_files('tokenizers')

# Torch (required by sentence-transformers)
hiddenimports += collect_submodules('torch')

# Additional dependencies
hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'numpy',
    'numpy.core',
    'sqlite3',
    'onnxruntime',
]

a = Analysis(
    ['rag_server.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='rag_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

