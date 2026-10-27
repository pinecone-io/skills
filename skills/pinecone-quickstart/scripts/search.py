#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pinecone==10.2.0",
#   "typer>=0.15.0",
# ]
# ///

import os
from enum import Enum
import typer
from pinecone import Pinecone

app = typer.Typer()

class Mode(str, Enum):
    meaning = "meaning"
    terms = "terms"

SCORE_TYPES = {Mode.meaning: "embed", Mode.terms: "text"}

@app.command()
def main(
    query: str = typer.Option(..., "--query", help="Text to search for"),
    mode: Mode = typer.Option(..., "--mode", help="meaning (semantic) or terms (exact terms, BM25)"),
    index: str = typer.Option("quickstart", "--index", help="Name of the document index to search"),
    namespace: str = typer.Option("__default__", "--namespace", help="Namespace to search"),
    top_k: int = typer.Option(3, "--top-k", help="Number of results to return"),
):
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        typer.echo("Error: PINECONE_API_KEY environment variable not set", err=True)
        raise typer.Exit(1)

    pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:index_quickstart")
    idx = pc.index(name=index)

    results = idx.documents.search(
        namespace=namespace,
        top_k=top_k,
        score_by=[{"type": SCORE_TYPES[mode], "fields": ["chunk_text"], "query": query}],
        include_fields=["chunk_text"],
    )

    if not results.matches:
        typer.echo("No matches")
        return
    for m in results.matches:
        typer.echo(f"{m._id} {m._score:.3f} {m.chunk_text}")

if __name__ == "__main__":
    app()
