#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pinecone==10.2.0",
#   "typer>=0.15.0",
# ]
# ///

import hashlib
import os
import time
from pathlib import Path
from urllib.parse import quote
from typing import Optional
import typer
from pinecone import Pinecone

app = typer.Typer()

SAMPLE_DOCUMENTS = [
    {"_id": "1", "chunk_text": "Refund requests must be submitted within 30 days of purchase.", "category": "policy"},
    {"_id": "2", "chunk_text": "Enterprise customers get support with a 4-hour response time.", "category": "policy"},
    {"_id": "3", "chunk_text": "Error E1042: the connection timed out after 30 seconds. Retry with a longer timeout.", "category": "log"},
    {"_id": "4", "chunk_text": "To reset your password, open Settings and choose Security.", "category": "support"},
    {"_id": "5", "chunk_text": "Order 88231 shipped on 2026-08-20 via express courier.", "category": "order"},
]

# The per-upsert cap for an index with an embed field.
BATCH_SIZE = 96
SKIP_DIRS = {"node_modules", "venv", "__pycache__", "site-packages", "dist", "build"}

def chunk(text: str, size: int = 500) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]

def safe_id(name: str) -> str:
    # Document IDs must be ASCII and at most 512 characters.
    doc_id = quote(name)
    return doc_id if len(doc_id) <= 480 else hashlib.sha256(name.encode()).hexdigest()[:32]

def source_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(
        p for p in source.rglob("*")
        if p.is_file()
        and p.suffix.lower() in (".md", ".txt")
        and not any(part.startswith(".") or part in SKIP_DIRS for part in p.relative_to(source).parts[:-1])
    )

def documents_from_source(source: Path) -> list[dict]:
    documents = []
    for path in source_files(source):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            typer.echo(f"Skipping {path}: not UTF-8 text", err=True)
            continue
        doc_id = safe_id(path.relative_to(source).as_posix() if source.is_dir() else path.name)
        documents += [
            {"_id": f"{doc_id}#{i}", "chunk_text": part}
            for i, part in enumerate(chunk(text))
            if part.strip()
        ]
    return documents

def wait_until_searchable(idx, namespace: str, last: dict, deadline_s: int = 60) -> bool:
    deadline = time.monotonic() + deadline_s
    while True:
        results = idx.documents.search(
            namespace=namespace,
            top_k=10,
            score_by=[{"type": "text", "fields": ["chunk_text"], "query": last["chunk_text"]}],
            include_fields=[],
        )
        if any(m.id == last["_id"] for m in results.matches):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(2)

@app.command()
def main(
    index: str = typer.Option("quickstart", "--index", help="Name of the document index to upsert into"),
    namespace: str = typer.Option("__default__", "--namespace", help="Namespace to upsert into"),
    source: Optional[Path] = typer.Option(None, "--source", help="A .md or .txt file, or a folder of them, to chunk and upsert instead of the sample documents"),
):
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        typer.echo("Error: PINECONE_API_KEY environment variable not set", err=True)
        raise typer.Exit(1)

    if source is None:
        documents = SAMPLE_DOCUMENTS
    elif not source.exists():
        typer.echo(f"Error: {source} does not exist", err=True)
        raise typer.Exit(1)
    else:
        documents = documents_from_source(source)
        if not documents:
            typer.echo(f"Error: no text found in .md or .txt files under {source}", err=True)
            raise typer.Exit(1)

    pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:upsert")
    idx = pc.index(name=index)

    for i in range(0, len(documents), BATCH_SIZE):
        try:
            idx.documents.upsert(namespace=namespace, documents=documents[i:i + BATCH_SIZE])
        except Exception as e:
            typer.echo(f"Error: upsert failed after {i} of {len(documents)} documents: {e}", err=True)
            raise typer.Exit(1)
    typer.echo(f"Upserted {len(documents)} documents into '{index}' (namespace: '{namespace}')")

    typer.echo("Waiting for the documents to become searchable...")
    if wait_until_searchable(idx, namespace, documents[-1]):
        typer.echo("Done")
    else:
        typer.echo("The documents aren't searchable yet. Wait a minute, then search again.", err=True)

if __name__ == "__main__":
    app()
