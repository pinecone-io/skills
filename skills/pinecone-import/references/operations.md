# Import operations

Start, monitor, list, and cancel imports. `scripts/run_import.py` wraps start + poll; the SDK/REST/console equivalents are here for when you need to do a step by hand or from another language.

All examples assume `PINECONE_API_KEY` is set in the environment and read by the client. Never hard-code the key.

## Create a compatible index

If the user doesn't already have a serverless index that matches their vectors' dimension/metric and is on a cloud compatible with their storage:

```python
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="your-key")  # reads PINECONE_API_KEY if omitted

if not pc.has_index("my-index"):
    pc.create_index(
        name="my-index",
        dimension=1024,            # must match your vectors
        metric="cosine",           # match how the vectors were trained
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
```

Pick `cloud` per the compatibility matrix in [preparing-data.md](preparing-data.md#cloud-compatibility) (S3 → `aws`, etc.).

## Start an import

`start_import` returns immediately with an operation `id`. `uri` is the directory prefix containing the namespace subdirectories — **not** a single file.

```python
from pinecone import Pinecone, ImportErrorMode

pc = Pinecone(api_key="your-key")
index = pc.index("my-index")

resp = index.start_import(
    uri="s3://my-bucket/import_data/",
    integration_id="a12b3d4c-...",        # omit for a public bucket
    error_mode=ImportErrorMode.ABORT,      # or "abort" / "continue"
)
print(resp.id)   # e.g. "101"
```

**Error mode:**
- `abort` — stop the whole import on the first record that fails to import. Best for a first run, so you discover format problems immediately.
- `continue` — skip bad records and keep going. **There is no per-record report** of what was skipped; you only see the final `records_imported` count via `describe_import`. Use once you trust the data.

### REST

```bash
curl "https://$INDEX_HOST/bulk/imports" \
  -H "Api-Key: $PINECONE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Pinecone-Api-Version: 2025-10" \
  -d '{
        "integrationId": "a12b3d4c-...",
        "uri": "s3://my-bucket/import_data/",
        "errorMode": { "onError": "continue" }
      }'
# → { "id": "101" }
```

`$INDEX_HOST` is the index's data-plane host (from `describe_index`).

### Console

Indexes page → your index → **... > Import data** → choose the storage integration (or "No integration (public bucket)"), enter the URI, pick an error-handling mode, **Start import**. Monitor under the index's **Imports** tab.

## Check status (describe)

```python
op = index.describe_import("101")
print(op.status)            # Pending | InProgress | Completed | Failed | Cancelled
print(op.percent_complete)  # e.g. 42.0
print(op.records_imported)  # e.g. 150000
print(op.error)             # error message if Failed
```

After the import loads the data, the **index builder** indexes it — records take **at least 10 minutes** to become queryable after `Completed`. A query that returns nothing right after completion is expected; wait and retry.

## Poll to completion

`scripts/run_import.py` does this for you. By hand:

```python
import time

op = index.describe_import("101")
while op.status not in ("Completed", "Failed", "Cancelled"):
    time.sleep(10)
    op = index.describe_import("101")

if op.status == "Completed":
    print(f"Imported {op.records_imported} records")
else:
    print(f"Import ended: {op.status} — {op.error}")
```

## List imports

```python
for imp in index.list_imports(limit=20):   # limit max 100; pagination handled automatically
    print(imp.id, imp.status, imp.percent_complete)
```

## Cancel an import

```python
index.cancel_import("101")
```

Or in the console: index → **Imports** tab → row **... menu > Cancel**.

## Import limits

Exceeding a limit returns an error naming the limit hit.

| Metric                                        | Limit   |
| --------------------------------------------- | ------- |
| Max namespaces per import                     | 10,000  |
| Max size per namespace                        | 500 GB  |
| Max total input data size (on-demand indexes) | 1 TB    |
| Max files per import                          | 100,000 |
| Max size per file                             | 10 GB   |

The total-data-size limit does not apply to indexes with [dedicated read nodes](https://docs.pinecone.io/guides/index-data/dedicated-read-nodes), which support larger imports.

## Troubleshooting

- **Import `Failed` immediately** — usually a schema problem (extra Parquet column, `metadata` not a JSON string, `values` length ≠ index dimension) or an unreadable bucket (wrong/missing Integration ID, or the role/service account lacks read access). Read `op.error`. Re-prepare with `scripts/to_parquet.py`, which enforces the schema.
- **Cross-cloud error** — index cloud and storage provider aren't a supported pair; see the [compatibility matrix](preparing-data.md#cloud-compatibility).
- **"Not supported for indexes with schemas"** — the target is an FTS/document-schema index; import only works on plain serverless indexes.
- **Records don't appear after `Completed`** — give it the ≥10-minute indexing window, then check `describe_index_stats()` for the per-namespace count before concluding anything's wrong.
- **Used `continue` and the count is lower than expected** — some records were skipped silently; re-run a sample with `abort` to surface the actual error.

Official troubleshooting: <https://docs.pinecone.io/guides/index-data/import-data#troubleshooting>
