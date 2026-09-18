#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12",
#   "pyarrow>=15.0",
# ]
# ///
"""Convert JSONL records into Pinecone-conformant, namespace-partitioned Parquet.

Pinecone's bulk importer rejects files that don't match its exact schema. A
hand-rolled conversion breaks in three predictable ways:

  1. Leftover source columns. The importer fails on ANY column other than
     id / values / sparse_values / metadata.
  2. metadata written as a nested Parquet struct. It must be a JSON STRING.
  3. Files dumped at the top level. The importer treats each subdirectory as a
     namespace; files must live under <out-dir>/<namespace>/.

This script does all three correctly and validates the input up front, aborting
loudly on the first bad row rather than producing a file the importer will
reject 20 minutes into an import.

Input is JSON Lines, one object per line:

    {"id": "1", "values": [0.1, 0.2], "metadata": {"year": 1984}}
    {"id": "2", "values": [0.3, 0.4]}
    {"id": "3", "values": [0.5, 0.6], "sparse_values": {"indices": [10, 88], "values": [2.0, 3.0]}}

`id` and `values` are required on every line. `metadata` (any JSON object) and
`sparse_values` ({"indices": [...], "values": [...]}) are optional.

Usage:

    uv run --script to_parquet.py \
      --input records.jsonl \
      --out-dir ./import_data \
      --namespace my_namespace

Writes ./import_data/my_namespace/0.parquet. Run once per namespace into the
same --out-dir, then upload the whole tree to your bucket, preserving structure.
Run with --help for all flags.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import typer

app = typer.Typer(add_completion=False)


def _fail(line_no: int, msg: str) -> None:
    typer.secho(f"line {line_no}: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _validate_row(line_no: int, rec: dict, dimension: int | None) -> int | None:
    """Validate one record; return the vector dimension seen (for consistency checks)."""
    if not isinstance(rec, dict):
        _fail(line_no, "not a JSON object")

    extra = set(rec) - {"id", "values", "sparse_values", "metadata"}
    if extra:
        _fail(line_no, f"unexpected key(s) {sorted(extra)} — fold extras into metadata")

    if not isinstance(rec.get("id"), str) or not rec["id"]:
        _fail(line_no, "missing or non-string 'id'")

    values = rec.get("values")
    if not isinstance(values, list) or not values or not all(
        isinstance(v, (int, float)) for v in values
    ):
        _fail(line_no, "'values' must be a non-empty array of numbers")
    if dimension is not None and len(values) != dimension:
        _fail(line_no, f"'values' length {len(values)} != {dimension} seen earlier")

    sv = rec.get("sparse_values")
    if sv is not None:
        if not isinstance(sv, dict) or set(sv) != {"indices", "values"}:
            _fail(line_no, "'sparse_values' must be {'indices': [...], 'values': [...]}")
        if len(sv["indices"]) != len(sv["values"]):
            _fail(line_no, "sparse_values indices/values length mismatch")

    md = rec.get("metadata")
    if md is not None and not isinstance(md, dict):
        _fail(line_no, "'metadata' must be a JSON object")

    return len(values)


@app.command()
def main(
    input: Path = typer.Option(..., "--input", "-i", help="JSONL file of records."),
    out_dir: Path = typer.Option(..., "--out-dir", "-o", help="Root output dir (the import URI maps here)."),
    namespace: str = typer.Option(..., "--namespace", "-n", help="Namespace = output subdirectory name."),
    file_name: str = typer.Option("0.parquet", "--file-name", help="Parquet file name within the namespace dir."),
) -> None:
    if not input.exists():
        typer.secho(f"input not found: {input}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    ids: list[str] = []
    values: list[list[float]] = []
    sparse: list[dict | None] = []
    metadata: list[str | None] = []
    dimension: int | None = None

    with input.open() as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                _fail(line_no, f"invalid JSON: {e}")
            dimension = _validate_row(line_no, rec, dimension)

            ids.append(rec["id"])
            values.append([float(v) for v in rec["values"]])
            sv = rec.get("sparse_values")
            sparse.append(
                None if sv is None else {
                    "indices": [int(i) for i in sv["indices"]],
                    "values": [float(v) for v in sv["values"]],
                }
            )
            md = rec.get("metadata")
            # metadata must be a JSON STRING column, not a nested struct.
            metadata.append(None if md is None else json.dumps(md, separators=(",", ":")))

    if not ids:
        typer.secho("no records found in input", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    sparse_type = pa.struct(
        [("indices", pa.list_(pa.uint32())), ("values", pa.list_(pa.float32()))]
    )
    table = pa.table(
        {
            "id": pa.array(ids, type=pa.string()),
            "values": pa.array(values, type=pa.list_(pa.float32())),
            "sparse_values": pa.array(sparse, type=sparse_type),
            "metadata": pa.array(metadata, type=pa.string()),
        }
    )

    dest_dir = out_dir / namespace
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file_name
    pq.write_table(table, dest)

    typer.secho(
        f"wrote {len(ids)} records (dim={dimension}) → {dest}",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"upload the contents of '{out_dir}' to your bucket, then import with "
        f"uri pointing at the uploaded '{out_dir.name}' directory."
    )


if __name__ == "__main__":
    app()
