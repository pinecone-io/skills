---
name: pinecone-quickstart
description: Interactive Pinecone quickstart for new developers. Choose between two paths - Database (create a document index with integrated embedding, upsert sample documents, and search them by meaning and by exact terms using bundled Python scripts) or Assistant (create a Pinecone Assistant for document Q&A). Use when a user wants to get started with Pinecone for the first time or wants a guided tour of Pinecone's tools.
---

# Pinecone Quickstart

Welcome! This skill walks you through your first Pinecone experience using the tools available to you. In this quickstart,
you will either search example data by meaning and by exact terms, or ask questions about your documents with Pinecone Assistant.

<<clarify_style>>

## Prerequisites

Before starting either path, verify the API key works by calling `list-indexes` via the Pinecone MCP. If it succeeds, proceed. If it fails with an auth error, ask the user to set their key:

<<api_key_setup>>

Then retry `list-indexes` to confirm.

If the MCP isn't available, skip this check. The bundled scripts check for the key themselves and fail fast without it.

## Step 0: Choose Your Path

Ask the user which path they want:

- **Database** – Build a document index that searches text by meaning and by exact terms. Best for developers who want to build search into their own app. Uses bundled Python scripts.
- **Assistant** – Build a document Q&A assistant. Best for users who want to upload files and ask questions with cited answers. No code required.

---

## Path A: Database Quickstart

This path builds the same index as the [docs quickstart](https://docs.pinecone.io/guides/get-started/quickstart): a document index whose one text field supports search by meaning and by exact terms. Pinecone embeds the text for you, so you send plain text, never vectors.

The Pinecone MCP can't create or search document indexes, so every step runs a bundled script with `uv`. If you're using a `.env` file, add `--env-file .env` after `uv run` in each command.

For each step, explain to the user what will happen. An overview is here:

1. Create a document index
2. Upsert 5 sample documents
3. Search by meaning
4. Search by exact terms, then explore further queries
5. Optionally upsert and search the user's own files
6. Offer the complete standalone script

### Step 1 – Create a Document Index

```bash
uv run scripts/create_index.py
```

The script creates an index named `quickstart` and waits until it's ready. If an index named `quickstart` already exists with the same schema, the script reuses it. If it exists with a different schema, the script stops: ask the user for another name and pass `--index <name>` to every script in this path.

**Explain to the user what's happening:**
- The index has one field, `chunk_text`, declared as `{"type": "string", "full_text_search": {"language": "en"}, "embed": {}}`
- `full_text_search` indexes the text for exact-term (BM25) search, and `embed` has Pinecone embed it for search by meaning, so one field supports both
- The empty `embed` config uses the default model, `llama-text-embed-v2`, at 1,024 dimensions
- This is the same default index the Pinecone console creates

### Step 2 – Upsert Sample Documents

```bash
uv run scripts/upsert.py
```

The script upserts 5 documents into the `__default__` namespace, then waits 10 seconds, because a new index takes a few seconds to make its first documents searchable.

**Explain to the user what's happening:**
- The 5 documents cover a refund policy, enterprise support, an error log (`Error E1042`), a password reset, and an order (`88231`)
- Each document has an `_id`, plain text on `chunk_text`, and a `category` field
- Pinecone embeds `chunk_text` on write. Fields outside the schema, like `category`, are stored as metadata you can filter on
- Documents are indexed asynchronously, which is why the script waits before you search

### Step 3 – Search by Meaning

```bash
uv run scripts/search.py --mode meaning --query "how do I get my money back?"
```

Display the results in a clean table: ID, score, and `chunk_text`. Document `1`, the refund policy, should rank first. If the search returns no matches, wait a few seconds and run it again.

**Explain to the user what's happening:**
- The search scores by `embed`: Pinecone embeds the query with the same model it used for the documents and ranks them by semantic similarity
- The question shares no words with the refund policy, but still finds it. That's search by meaning

### Step 4 – Search by Exact Terms

```bash
uv run scripts/search.py --mode terms --query "E1042"
```

Display the results the same way. Only document `3`, the one that contains `E1042`, should match.

**Explain to the user what's happening:**
- The search scores by `text`: it ranks the same field by BM25 keyword relevance, so an exact identifier like an error code surfaces the document that contains it
- This is a separate search from Step 3. Each returns its own ranking, and the scores are on different scales, so don't compare them across searches
- To merge the two rankings into one list, use [reciprocal rank fusion](https://docs.pinecone.io/guides/search/reciprocal-rank-fusion) in your own code

Always present these as two separate searches. Don't describe them as combined, fused, or hybrid search.

**Offer to explore further:** Ask the user if they'd like to try another query:
- Option A: `--mode meaning --query "I can't log in to my account"`, which should rank the password reset (`4`) first
- Option B: `--mode terms --query "88231"`, which should match only the order (`5`)
- Option C: `--mode terms --query "how do I get my money back?"`, the Step 3 question as an exact-terms search. The refund policy doesn't match, because it shares no words with the question
- Option D: No thanks, move on

Run whichever query they choose and display the results the same way. The user can also try their own queries in either mode. After each result, point out why those documents surfaced.

### Step 5 – Use Your Own Files (Optional)

Ask the user if they want to search their own files. If not, skip to Step 6.

If yes, ask for the path to a file or folder. The script reads `.md` and `.txt` files directly:

```bash
uv run scripts/upsert.py --source ./your-docs
```

For other formats (PDF, DOCX, HTML, and so on), extract the text to `.md` or `.txt` files first using a parser of the user's choice, then pass those files to `--source`.

**Explain to the user what's happening:**
- Pinecone doesn't extract or chunk files, so the script splits each file's text into 500-character chunks before upserting. The embedding model reads only the first 2,048 tokens of a value, so chunks need to stay well under that
- Each chunk ID starts with its file path (`handbook.md#0`, `handbook.md#1`, ...), so all of a file's chunks can be fetched, replaced, or deleted together later
- An index with an `embed` field accepts at most 96 documents per upsert, so the script sends the chunks in batches of 96
- Bulk import isn't supported on an index with an `embed` field. For a large dataset in Python, `documents.batch_upsert` sends batches in parallel and retries failures

Then ask the user for a question about their files and run it in either mode with `scripts/search.py`, the same way as Steps 3 and 4. The sample documents stay in the index, so they can show up in results too.

### Step 6 – Wrap Up

Congratulate the user on completing the quickstart. Ask if they'd like a standalone Python script that does everything in one go: create the index, upsert the sample documents, and run both searches.

If yes, copy it to their working directory:

```bash
cp scripts/quickstart_complete.py ./pinecone_quickstart.py
```

Tell the user:
- The script is at `./pinecone_quickstart.py`
- Run it with: `uv run pinecone_quickstart.py`
- It uses `uv` inline dependencies, so no separate install is needed
- It requires `pinecone` Python SDK 10.1.0 or later, which integrated embedding on a document index needs
- They can swap in their own documents to build something real

For query syntax, phrase matching, and text-match filters, point them to `pinecone-full-text-search`.

---

## Path B: Assistant Quickstart

Guide the user through the Pinecone Assistant workflow using the existing pinecone-assistant skill:

### Step 1 – Check for Documents

Before anything else, ask the user if they have files to upload. Pinecone Assistant accepts `.pdf`, `.md`, `.txt`, and `.docx` files — a single file or a folder of files both work.

**If they have files:** ask for the path and proceed to Step 2.

**If they don't have files:** offer two options:
- **Generate sample docs** — create a few short markdown files in `./sample-docs/` so they can complete the quickstart right now. Ask what topics they'd like (or default to: a product FAQ, a short how-to guide, and a brief company overview). Write 3 files, each 150–250 words.
- **Come back later** — let them know they can return once they have documents and pick up from Step 2.

### Step 2 – Create an Assistant

Invoke `pinecone-assistant` or run (add `--env-file .env` if using a `.env` file):
```bash
uv run ../pinecone-assistant/scripts/create.py --name my-assistant
```

Explain: The assistant is a fully managed RAG service — upload documents, ask questions, get cited answers.

### Step 3 – Upload Documents

Invoke `pinecone-assistant` or run (add `--env-file .env` if using a `.env` file):
```bash
uv run ../pinecone-assistant/scripts/upload.py --assistant my-assistant --source ./your-docs
```

Explain: Pinecone handles chunking, embedding, and indexing automatically — no configuration needed.

### Step 4 – Chat with the Assistant

Invoke `pinecone-assistant` or run (add `--env-file .env` if using a `.env` file):
```bash
uv run ../pinecone-assistant/scripts/chat.py --assistant my-assistant --message "What are the main topics in these documents?"
```

Explain: Responses include citations with source file and page number.

### Next Steps for Assistant

- Invoke `pinecone-assistant` to keep the assistant up to date as documents change
- Use the pinecone-assistant skill to retrieve raw context snippets for custom workflows
- Every assistant is also an MCP server — see https://docs.pinecone.io/guides/assistant/mcp-server

---

## Troubleshooting

**`PINECONE_API_KEY` not set**

<<api_key_setup>>

Restart your IDE or agent session after setting the key.

**MCP tools not available**
- The MCP is only used for the `list-indexes` key check. The Database path runs entirely on bundled scripts
- To set up the MCP anyway, verify the Pinecone MCP server is configured in your IDE's MCP settings, and check that `PINECONE_API_KEY` is set before the MCP server starts

**Index already exists**
- `create_index.py` reuses a `quickstart` index that has the quickstart schema, and the upsert script is safe to re-run: it overwrites documents with the same IDs
- If `quickstart` exists with a different schema, pass `--index <name>` to every script, or delete it with `pc index delete -n quickstart` via the CLI

**Search returns no matches right after upserting**
- Documents are indexed asynchronously. Wait a few seconds and run the search again

**`uv` not installed**
See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

## Further Reading

- Quickstart docs: https://docs.pinecone.io/guides/get-started/quickstart
- Integrated embedding: https://docs.pinecone.io/guides/search/integrated-embedding
- Full-text search: https://docs.pinecone.io/guides/search/full-text-search
- Python SDK: https://docs.pinecone.io/reference/sdks/python/overview
- MCP server: https://docs.pinecone.io/guides/operations/mcp-server
