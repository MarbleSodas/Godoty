import os, sys, hashlib, json
from pathlib import Path
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

# LangChain + Chroma (local)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

app = FastAPI(title="Godoty RAG Sidecar")

MODEL_NAME = os.getenv("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RAG_DB_ROOT = Path(os.getenv("RAG_DB_ROOT", str(Path.home() / ".godoty" / "rag_db")))
RAG_DB_ROOT.mkdir(parents=True, exist_ok=True)

SUPPORTED_EXTS = {".gd", ".tscn", ".tres", ".cfg", ".ini", ".json", ".md", ".txt", ".toml", ".yaml", ".yml"}

# Global embedding fn (loaded once)
_embeddings = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=MODEL_NAME)
    return _embeddings


def norm_path(p: str) -> str:
    ap = str(Path(p).expanduser().resolve())
    return ap.lower().replace("\\", "/") if os.name == "nt" else ap


def project_store_dir(project_path: str) -> Path:
    key = hashlib.sha256(norm_path(project_path).encode()).hexdigest()[:16]
    return RAG_DB_ROOT / key


def walk_project_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
    return files


class IndexRequest(BaseModel):
    project_path: str
    force_rebuild: bool = False
    chunk_size: int = 1200
    chunk_overlap: int = 200


class SearchRequest(BaseModel):
    project_path: str
    query: str
    k: int = 5


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "db_root": str(RAG_DB_ROOT)}


@app.post("/index-project")
async def index_project(req: IndexRequest):
    root = Path(req.project_path).expanduser().resolve()
    if not root.exists():
        return {"error": f"Project path not found: {root}"}

    files = walk_project_files(root)
    splitter = RecursiveCharacterTextSplitter(chunk_size=req.chunk_size, chunk_overlap=req.chunk_overlap)

    docs: List[Document] = []
    ids: List[str] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        chunks = splitter.split_text(text)
        for i, ch in enumerate(chunks):
            docs.append(Document(page_content=ch, metadata={"source": str(f)}))
            ids.append(hashlib.sha1(f"{f}::{i}".encode()).hexdigest())

    persist_dir = project_store_dir(req.project_path)
    persist_dir.mkdir(parents=True, exist_ok=True)
    embeddings = get_embeddings()

    if req.force_rebuild and persist_dir.exists():
        # Recreate collection
        try:
            import shutil
            shutil.rmtree(persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    if docs:
        # Upsert into Chroma persisted store
        try:
            vs = Chroma(persist_directory=str(persist_dir), embedding_function=embeddings)
            vs.add_documents(docs, ids=ids)
            vs.persist()
            count = len(docs)
        except Exception:
            # Fallback: fresh create
            vs = Chroma.from_documents(documents=docs, embedding=embeddings, persist_directory=str(persist_dir))
            vs.persist()
            count = len(docs)
    else:
        count = 0

    return {"status": "indexed", "files": len(files), "chunks": count, "persist_directory": str(persist_dir)}


@app.post("/search-project")
async def search_project(req: SearchRequest):
    persist_dir = project_store_dir(req.project_path)
    if not persist_dir.exists():
        return {"results": [], "error": "No index for this project yet"}

    embeddings = get_embeddings()
    vs = Chroma(persist_directory=str(persist_dir), embedding_function=embeddings)
    try:
        docs_and_scores = vs.similarity_search_with_score(req.query, k=req.k)
    except Exception as e:
        return {"results": [], "error": f"search_failed: {e}"}

    results = []
    for doc, score in docs_and_scores:
        results.append({
            "source": doc.metadata.get("source", "N/A"),
            "content": doc.page_content,
            "score": float(score),
        })
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("RAG_PORT", "5001"))
    uvicorn.run(app, host="127.0.0.1", port=port)

