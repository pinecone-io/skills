# Preparing data for import

Pinecone's importer reads **Parquet files** arranged in a **specific directory layout**, with a **fixed column schema**. Get any of these wrong and the import fails or silently skips records. `scripts/to_parquet.py` produces conformant output from JSONL; this file documents the contract it satisfies so you can verify it (or hand-build if you must).

## Parquet column schema

Each Parquet file holds one row per record. The columns are exactly:

| Column          | Parquet type                                          | Required | Notes |
| --------------- | ----------------------------------------------------- | -------- | ----- |
| `id`            | `STRING`                                              | Yes      | Unique record identifier. |
| `values`        | `LIST<FLOAT>`                                          | Yes      | The dense vector. Length must equal the index's dimension. |
| `sparse_values` | `STRUCT<indices: LIST<UINT_32>, values: LIST<FLOAT>>` | No       | Sparse vector. Use `NULL` to omit on specific rows. |
| `metadata`      | `STRING`                                              | No       | Metadata as a **JSON string** (not a Parquet struct). Use `NULL` to omit on specific rows. |

> **The file must contain no other columns.** Any extra column fails the import. Don't leave your source's original columns in — fold everything you want to keep into the `metadata` JSON string.

Example rows (logical view):

```
id | values                   | sparse_values                                        | metadata
---------------------------------------------------------------------------------------------------------
1  | [3.82, 2.48, -4.15, ...] | {"indices": [10, 88, 102], "values": [2.0, 3.0, 4.0]} | {"year": 1984, "title": "Example1"}
2  | [1.82, 3.48, -2.15, ...] | NULL                                                  | {"year": 1990, "title": "Example2"}
```

Note `metadata` is the literal JSON text `{"year": 1984, ...}`, stored in a string column — **not** a nested Parquet structure.

## JSONL input format (what the helper accepts)

`scripts/to_parquet.py` reads JSON Lines — one JSON object per line — and emits conformant Parquet. Each line:

```json
{"id": "1", "values": [0.1, 0.2, 0.3], "metadata": {"year": 1984, "title": "Example1"}}
{"id": "2", "values": [0.4, 0.5, 0.6]}
{"id": "3", "values": [0.7, 0.8, 0.9], "sparse_values": {"indices": [10, 88], "values": [2.0, 3.0]}, "metadata": {"genre": "doc"}}
```

- `id` (string) and `values` (array of numbers) are required on every line.
- `metadata` is a normal JSON object in the input; the helper serializes it to the required JSON-string column. Omit it entirely to store no metadata.
- `sparse_values`, when present, is `{"indices": [...], "values": [...]}` with equal-length arrays.
- The helper validates these rules and aborts loudly on the first bad line rather than producing a file the importer will reject.

If your data starts as CSV or a different shape, convert it to this JSONL first (any small script will do), then run the helper.

## Namespace directory layout

The import `uri` points to a **directory prefix**. Inside it, **each subdirectory is a namespace**, and the Parquet files for that namespace live directly in it. Records are imported into the namespace named by their subdirectory.

```
<BUCKET_OR_CONTAINER>/
└── import_data/                 ← this is the import `uri`
    ├── example_namespace1/
    │   ├── 0.parquet
    │   ├── 1.parquet
    │   └── 2.parquet
    └── example_namespace2/
        ├── 3.parquet
        └── 4.parquet
```

- To import everything into one namespace, use a single subdirectory.
- `scripts/to_parquet.py --namespace <name>` writes into the correct subdirectory for you; run it once per namespace into the same `--out-dir`, then upload the whole `--out-dir` tree to your bucket preserving the structure.
- File names within a namespace don't matter, only that they're `.parquet` and in the right subdirectory.

## Cloud compatibility

The index's cloud must support the storage provider you import from:

|                              | → **AWS** index | → **GCP** index | → **Azure** index |
| ---------------------------- | :-------------: | :-------------: | :---------------: |
| from **AWS S3**              |        ✅        |        ❌        |         ❌         |
| from **Google Cloud Storage**|        ✅        |        ✅        |         ❌         |
| from **Azure Blob Storage**  |        —        |        —        |         ✅         |

If your storage and index clouds aren't a supported pair, you can't import directly — create the index on a compatible cloud, or move the data. When in doubt, confirm against the matrix in the [official import guide](https://docs.pinecone.io/guides/index-data/import-data).

## URI formats

- **S3:** `s3://BUCKET_NAME/IMPORT_DIR`
- **Google Cloud Storage:** `gs://BUCKET_NAME/IMPORT_DIR`
- **Azure Blob Storage:** `https://STORAGE_ACCOUNT.blob.core.windows.net/CONTAINER_NAME/IMPORT_DIR`

The URI is the directory that *contains* the namespace subdirectories.
