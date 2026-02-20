---
name: quickstart
description: Interactive Pinecone quickstart for new developers. Choose between two paths - Database (create an integrated index, upsert data, and query using Pinecone MCP + Python) or Assistant (create a Pinecone Assistant for document Q&A). Use when a user wants to get started with Pinecone for the first time or wants a guided tour of Pinecone's tools.
---

# Pinecone Quickstart

Welcome! This skill walks you through your first Pinecone experience using the tools available to you.

## Prerequisites

Before starting either path, verify:
1. **`PINECONE_API_KEY`** is set in the environment. Get a free key at https://app.pinecone.io/?sessionType=signup
2. For the **Database path**: the Pinecone MCP server must be configured and available

## Step 0: Choose Your Path

Use AskUserQuestion (or any available user-input tool) to ask the user which path they want:

- **Database** – Build a vector search index. Best for developers who want to store and search embeddings. Uses the Pinecone MCP + a Python upsert script.
- **Assistant** – Build a document Q&A assistant. Best for users who want to upload files and ask questions with cited answers. No code required.

---

## Path A: Database Quickstart

### Step 1 – Verify MCP is Available

Attempt to call `list-indexes` from the Pinecone MCP. If it fails or tools are unavailable:
- Tell the user the MCP server needs to be configured
- Point them to: https://docs.pinecone.io/reference/tools/mcp

If it succeeds, proceed.

### Step 2 – Create an Integrated Index

Use the MCP `create-index-for-model` tool to create a serverless index with integrated embeddings:

```
name: quickstart-skills
cloud: aws
region: us-east-1
embed:
  model: llama-text-embed-v2
  fieldMap:
    text: chunk_text
```

**Explain to the user what's happening:**
- An *integrated index* uses a built-in Pinecone embedding model (`llama-text-embed-v2`)
- This means you send plain text and Pinecone handles the embedding automatically
- The `field_map` tells Pinecone which field in your records contains the text to embed

Wait for the index to become ready before proceeding. Waiting a few seconds is sufficient.

### Step 3 – Upsert Sample Data

Run the bundled upsert script to seed the index with sample records:

```bash
uv run scripts/upsert.py --index quickstart
```

**Explain to the user what's happening:**
- The script uploads 8 sample records about famous world landmarks
- Each record has an `_id`, a `chunk_text` field (the text that gets embedded), and a `category` field
- This is the same structure you'd use for your own data — just replace the records

### Step 4 – Query with the MCP

Use the MCP `search-records` tool to run a semantic search:

```
index: quickstart
namespace: example-namespace
query:
  topK: 3
  inputs:
    text: "Famous historical structures and monuments"
```

Display the results in a clean table: ID, score, and `chunk_text`.

**Explain to the user what's happening:**
- You sent plain text — no vector math required
- Pinecone embedded your query using the same model as the index
- Results are ranked by semantic similarity, not keyword match

### Step 5 – Try Reranking (Optional)

Use AskUserQuestion to ask if they want to try reranking.

If yes, use `search-records` again with reranking enabled:

```
rerank:
  model: bge-reranker-v2-m3
  rankFields: [chunk_text]
  topN: 3
```

**Explain**: Reranking runs a second-pass model over the results to improve relevance ordering.

### Step 6 – Copy the Complete Script

Tell the user:

> "You just completed the Pinecone database quickstart! Here's a standalone Python script that does everything in one go — create, upsert, query, and rerank. It's been copied to your project."

Copy the complete script into their working directory:

```bash
cp scripts/quickstart_complete.py ./pinecone_quickstart.py
```

Then tell the user:
- The script is at `./pinecone_quickstart.py`
- Run it with: `uv run pinecone_quickstart.py`
- It uses `uv` inline dependencies — no separate install needed
- They can modify the `records` list with their own data to build something real

---

## Path B: Assistant Quickstart

Guide the user through the Pinecone Assistant workflow using the existing assistant skills:

### Step 1 – Create an Assistant

Invoke `pinecone:assistant-create` or run:
```bash
uv run ../assistant/scripts/create.py --name my-assistant
```

Explain: The assistant is a fully managed RAG service — upload documents, ask questions, get cited answers.

### Step 2 – Upload Documents

Invoke `pinecone:assistant-upload` or run:
```bash
uv run ../assistant/scripts/upload.py --assistant my-assistant --source ./your-docs
```

Explain: Point to any local folder with `.pdf`, `.md`, `.txt`, or `.docx` files. Pinecone handles chunking, embedding, and indexing automatically.

### Step 3 – Chat with the Assistant

Invoke `pinecone:assistant-chat` or run:
```bash
uv run ../assistant/scripts/chat.py --assistant my-assistant --message "What are the main topics in these documents?"
```

Explain: Responses include citations with source file and page number.

### Next Steps for Assistant

- Use `pinecone:assistant-sync` to keep the assistant up to date as documents change
- Use `pinecone:assistant-context` to retrieve raw context snippets for custom workflows
- Every assistant is also an MCP server — see https://docs.pinecone.io/guides/assistant/mcp-server

---

## Troubleshooting

**`PINECONE_API_KEY` not set**
```bash
export PINECONE_API_KEY="your-key-here"
```
Then restart your IDE/agent session.

**MCP tools not available**
- Verify the Pinecone MCP server is configured in your IDE's MCP settings
- Check that `PINECONE_API_KEY` is set before the MCP server starts

**Index already exists**
- The upsert script is safe to re-run — it will upsert over existing records
- Or delete and recreate: use `pc index delete -n quickstart` via the CLI

**`uv` not installed**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Further Reading

- Quickstart docs: https://docs.pinecone.io/guides/get-started/quickstart
- Integrated indexes: https://docs.pinecone.io/guides/index-data/create-an-index
- Python SDK: https://docs.pinecone.io/guides/get-started/python-sdk
- MCP server: https://docs.pinecone.io/reference/tools/mcp
