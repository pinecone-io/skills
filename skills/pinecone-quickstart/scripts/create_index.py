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
import typer
from pinecone import Pinecone, SchemaBuilder

app = typer.Typer()

@app.command()
def main(
    index: str = typer.Option("quickstart", "--index", help="Name of the document index to create"),
):
    api_key = os.environ.get("PINECONE_API_KEY")
    if not api_key:
        typer.echo("Error: PINECONE_API_KEY environment variable not set", err=True)
        raise typer.Exit(1)

    pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:index_quickstart")

    if pc.indexes.exists(name=index):
        schema = pc.indexes.describe(name=index).schema
        field = schema.fields.get("chunk_text") if schema else None
        if not (getattr(field, "full_text_search", None) and getattr(field, "embed", None)):
            typer.echo(
                f"Error: index '{index}' already exists but has no 'chunk_text' field with "
                "full_text_search and embed. Pass --index with a different name.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"Index '{index}' already exists with the quickstart schema, reusing it")
    else:
        schema = (
            SchemaBuilder()
              .add_string_field("chunk_text", full_text_search={"language": "en"}, embed={})
              .build()
        )
        pc.indexes.create(name=index, schema=schema)
        typer.echo(f"Creating index '{index}'...")

    while not pc.indexes.describe(name=index).status.ready:
        time.sleep(2)
    typer.echo(f"Index '{index}' is ready")

if __name__ == "__main__":
    app()
