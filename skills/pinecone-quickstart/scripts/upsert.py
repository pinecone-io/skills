#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pinecone==10.2.0",
#   "typer>=0.15.0",
# ]
# ///

import os
import time
from pathlib import Path
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

def chunk(text: str, size: int = 500) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]

def documents_from_source(source: Path) -> list[dict]:
    files = [source] if source.is_file() else sorted(
        p for p in source.rglob("*") if p.suffix.lower() in (".md", ".txt")
    )
    documents = []
    for path in files:
        doc_id = str(path.relative_to(source)) if source.is_dir() else path.name
        text = path.read_text(encoding="utf-8")
        documents += [
            {"_id": f"{doc_id}#{i}", "chunk_text": part}
            for i, part in enumerate(chunk(text))
            if part.strip()
        ]
    return documents

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
        idx.documents.upsert(namespace=namespace, documents=documents[i:i + BATCH_SIZE])
    typer.echo(f"Upserted {len(documents)} documents into '{index}' (namespace: '{namespace}')")

    typer.echo("Waiting 10 seconds for the documents to become searchable...")
    time.sleep(10)
    typer.echo("Done")

if __name__ == "__main__":
    app()
