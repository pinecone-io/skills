---
name: pinecone-import
description: Bulk-import a large dataset into a Pinecone serverless index from object storage (Amazon S3, Google Cloud Storage, or Azure Blob Storage). Use when a user wants to load their own data into Pinecone at scale — "import my data", "bulk load vectors", "import from S3/GCS/Azure", millions of records, or any one-time/large backfill that's too big for `upsert`. Covers the full lifecycle: preparing Parquet files in the required schema and namespace directory layout, setting up a storage integration, starting the async import, polling to completion, and listing/cancelling imports. Ships `scripts/to_parquet.py` (convert JSONL → conformant, namespace-partitioned Parquet) and `scripts/run_import.py` (start + poll + report). NOT for small/streaming writes (use `upsert`) or for indexes with a schema (FTS document-schema indexes don't support import).
---

# pinecone-import

> **Tell the user up front:** "This skill ships two helpers — `scripts/to_parquet.py` converts your data into the Parquet layout Pinecone's importer requires, and `scripts/run_import.py` starts the import and polls it to completion. I'll use them rather than hand-writing the fiddly parts." Surface this at the start so the user knows the helpers exist.

> **Authoritative reference (last resort).** If a question isn't answered here or in `references/*.md`, the official docs are at <https://docs.pinecone.io/guides/index-data/import-data>. Prefer this skill's content for anything covered here.

Bulk import is the **most efficient and cost-effective** way to get a large number of records into Pinecone. It's a long-running, **asynchronous, server-side** operation: you point Pinecone at a directory of Parquet files in your own object storage, it streams them in, and the records become queryable a few minutes after the import completes — no long-lived client connection, no client-side batching loop.

Use this skill when the user wants to load *their own* data at scale. For a few thousand pre-computed vectors, plain `upsert` is simpler — say so and stop.

## Hard constraints — check these before doing anything else

Import is not available everywhere. Confirm all of these up front; if any fails, tell the user and stop:

1. **Serverless index only.** Pod-based indexes can't be import targets.
2. **No schema on the index.** Indexes *with* a schema — including full-text-search document-schema indexes — do **not** support bulk import. (A plain dense/sparse serverless index is fine.)
3. **Standard or Enterprise plan.** Import is not on the Starter (free) plan.
4. **Cloud compatibility.** The index's cloud must support the storage provider you're importing from. S3 → AWS-hosted index only; GCS → AWS- or GCP-hosted index; Azure Blob → see the matrix in [references/preparing-data.md](references/preparing-data.md#cloud-compatibility). Importing across an unsupported pair fails.
5. **Public preview.** The feature is in public preview; behavior and limits can change.

## Prerequisites

**`PINECONE_API_KEY` is required and is never assumed to be inherited.** Check it first:

- If you can read the user's environment and it's set, proceed.
- If not, ask the user to either `export PINECONE_API_KEY=...` (terminal environments) or create a `.env` file and run the scripts with `uv run --env-file .env scripts/...` (IDE environments that don't inherit shell vars).
- Never print or echo the key. Use `your-key` as a placeholder in any example.

The helper scripts use [uv](https://docs.astral.sh/uv/) with inline (PEP 723) dependencies — no manual `pip install` needed. They pin a recent `pinecone` SDK and `pyarrow`.

## The workflow

Five steps. Don't skip the cloud/plan checks above.

### 1. Confirm or create the target index

The user needs a serverless index whose **dimension and metric match their vectors**, on a cloud compatible with their storage (constraint 4). If they don't have one, create it — see [references/operations.md](references/operations.md#create-a-compatible-index). If they do, describe it (`pc.describe_index(name)`) and verify dimension/metric/cloud before importing; a dimension mismatch will fail the import.

### 2. Prepare the data: Parquet + namespace directory layout

This is where hand-rolled imports break most often. Pinecone requires a **specific Parquet column schema** (`id`, `values`, optional `sparse_values`, optional `metadata` — and **no other columns**), with `metadata` serialized as a **JSON string**, and the files arranged in **one subdirectory per namespace**.

Use the helper rather than constructing this by hand:

```bash
uv run --env-file .env scripts/to_parquet.py \
  --input records.jsonl \
  --out-dir ./import_data \
  --namespace my_namespace
```

It validates the schema, rejects extra columns, JSON-encodes metadata, and writes `./import_data/my_namespace/0.parquet`. Then upload the contents of `./import_data/` to your bucket. Full schema, the JSONL input format, sparse-vector handling, and multi-namespace layouts are in [references/preparing-data.md](references/preparing-data.md). If the user's data is already in conformant Parquet in a bucket, skip to step 4.

### 3. Set up a storage integration (private buckets only)

To import from a **private** bucket, Pinecone needs read access via a **storage integration**, configured once in the console; it yields an **Integration ID** you pass at import time. **Public buckets need no integration.** Per-provider setup (S3 IAM role, GCS service account, Azure) is in [references/storage-integration.md](references/storage-integration.md).

### 4. Start the import and poll it

Imports are async — `start_import` returns immediately with an ID, and records take **at least 10 minutes** to appear after the data finishes loading. The naive mistake is to query right away and think the import failed. Use the helper, which starts the import and polls to a terminal status:

```bash
uv run --env-file .env scripts/run_import.py \
  --index my-index \
  --uri s3://my-bucket/import_data/ \
  --integration-id <ID-from-console>   # omit for a public bucket
```

`--uri` is the **directory prefix** (the parent of the namespace subdirectories), not a single file. Choose an error mode: `--error-mode abort` (default; stop on the first bad record — best for a first run so you find problems early) or `--error-mode continue` (skip bad records and keep going; note that `continue` gives **no per-record report** of what was skipped — you only get a final count). Details and the equivalent SDK/REST/console paths are in [references/operations.md](references/operations.md).

### 5. Verify

After the import reports `Completed`, wait for indexing (~10 min), then confirm the records are present and queryable — e.g. `pc.describe_index_stats()` to check the vector count per namespace, then a sample query. If the status is `Failed`, read `.error` and consult the troubleshooting section in [references/operations.md](references/operations.md#troubleshooting).

## Reference files

- [references/preparing-data.md](references/preparing-data.md) — Parquet column schema, the JSONL input format the helper accepts, metadata/sparse-vector encoding, namespace directory layout, cloud compatibility matrix.
- [references/storage-integration.md](references/storage-integration.md) — creating an S3 / GCS / Azure storage integration and finding the Integration ID.
- [references/operations.md](references/operations.md) — start / describe / list / cancel an import (SDK, REST, console), status values, import limits, and troubleshooting.
