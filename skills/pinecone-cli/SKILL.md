---
name: pinecone-cli
description: Guide for using the Pinecone CLI (pc) to manage Pinecone resources from the terminal. The CLI supports ALL index types (standard, integrated, sparse) and all vector operations — unlike the MCP which only supports integrated indexes. Use for authentication, generating api keys, batch operations, vector management, backups, namespaces, CI/CD automation, and full control over Pinecone resources.
argument-hint: install | auth | index [op] | vector [op] | backup | namespace
---

# Pinecone CLI (`pc`)

Manage Pinecone from the terminal. The CLI is especially valuable for:

- vector operations across **all index types** — something the MCP currently can't do.
- authentication and API key management: logging in, generating keys, and switching contexts (orgs/projects).

**Extremely important: always use the json flag and the latest version of the CLI**
Most commands in the CLI support a `-j` or `--json` flag that outputs structured JSON instead of human-readable text. This is critical for reliably parsing output in scripts and agent loops. Always use the JSON output when invoking CLI commands from code, especially during authetnication flows.

## CLI vs MCP

| | CLI | MCP |
|---|---|---|
| Index types | All (standard, integrated, sparse) | Integrated only |
| Vector ops (upsert, query, fetch, update, delete) | ✅ | ❌ |
| Text search on integrated indexes | ✅ | ✅ |
| Backups, namespaces, org/project mgmt | ✅ | ❌ |
| CI/CD / scripting | ✅ | ❌ |

---


## Setup when invoked
When a user invokes this skill, check if `pc` is installed and authenticated by running these two commands:

```bash
pc version --json
pc auth status --json
```

- If `pc version` fails, the CLI is not installed — install it using the steps below.
- If `pc auth status` returns an empty `access_token`, the user is not authenticated — follow the Authenticate section below.

It is also important to check that we have the latest version of the CLI installed. If the version is outdated or the CLI is not installed, install/upgrade as follows:

### Install (macOS)
```bash
brew uninstall pinecone-io/tap/pinecone
brew install --cask pinecone-io/tap/pinecone
```

Other platforms (Linux, Windows) — download from [GitHub Releases](https://github.com/pinecone-io/cli/releases).

### Authenticate

For agent and IDE sessions, always use `--json` mode. Unlike the interactive `pc login`, the JSON mode is non-blocking — it returns immediately with a login URL instead of waiting for the browser flow to complete. This means you can present the URL and prompt the user to confirm they've logged in at the same time, so the user clicks the link while the confirmation prompt is already waiting for them:

**Step 1** — Start the login flow:
```bash
pc login --json
```
Returns:
```json
{
    "status": "pending",
    "url": "<example-oauth-url>",
    "session_id": "...",
    "description": "Navigate to the URL to complete the OAuth authorization flow, then call this command again to retrieve credentials."
}
```
Present the `url` to the user so they can open it in a browser and complete the OAuth flow. Then, use whatever user-prompting or question tool is available in your environment to ask the user to confirm they have completed the login before proceeding.

**Step 2** — Once the user confirms, retrieve credentials:
```bash
pc login --json
```
Returns:
```json
{
    "status": "authenticated",
    "email": "user@example.com",
    "org_id": "...",
    "org_name": "my-org",
    "project_id": "...",
    "project_name": "my-project"
}
```

Inform the user which organization and project they are now authenticated to (from the `org_name` and `project_name` fields). If they need to switch, use:
```bash
pc target -o "my-org" -p "my-project"
```

**Other authentication methods:**
```bash
# Service account (recommended for CI/CD)
pc auth configure --client-id "$PINECONE_CLIENT_ID" --client-secret "$PINECONE_CLIENT_SECRET"

# API key (quick testing)
pc config set-api-key $PINECONE_API_KEY
```

Check status: `pc auth status` · `pc target --show`

### Authenticating the CLI does not set `PINECONE_API_KEY`: Here's how to make an API key for scripts and agents

`pc login` authenticates the CLI tool itself — it does **not** set `PINECONE_API_KEY` in your environment. Python scripts, Node.js SDKs, and other tools that use the Pinecone SDK need `PINECONE_API_KEY` set separately.

**If the user already has an API key**, they should export it in their terminal before starting the agent session:
```bash
export PINECONE_API_KEY="your-key"
```

**If the user needs a new key mid-session**, use the CLI to create one and write it to a `.env` file. This works across shell invocations in agent environments where each command runs in a separate process:

```bash
pc api-key create --name agent-sdk-key --json | jq -r '"PINECONE_API_KEY=" + .value' > .env
```

Then run scripts with the `--env-file` flag:
```bash
uv run --env-file .env scripts/...
```

> **Important:** Remind the user to add `.env` to their `.gitignore` to avoid committing API keys to their repository.

---

## Common Commands

| Task | Command |
|---|---|
| List indexes | `pc index list` |
| Create serverless index | `pc index create -n my-index -d 1536 -m cosine -c aws -r us-east-1` |
| Index stats | `pc index stats -n my-index` |
| Upload vectors from file | `pc index vector upsert -n my-index --file ./vectors.json` |
| Query by vector | `pc index vector query -n my-index --vector '[0.1, ...]' -k 10 --include-metadata` |
| Query by vector ID | `pc index vector query -n my-index --id "doc-123" -k 10` |
| Fetch vectors by ID | `pc index vector fetch -n my-index --ids '["vec1","vec2"]'` |
| List vector IDs | `pc index vector list -n my-index` |
| Delete vectors by filter | `pc index vector delete -n my-index --filter '{"genre":"classical"}'` |
| List namespaces | `pc index namespace list -n my-index` |
| Create backup | `pc backup create -i my-index -n "my-backup"` |
| JSON output (for scripting) | Add `-j` to any command |

---

## Interesting Things You Can Do

### Query with custom vectors (not just text)
Unlike the MCP, the CLI lets you query any index with raw vector values — useful when you generate embeddings externally (OpenAI, HuggingFace, etc.):
```bash
pc index vector query -n my-index \
  --vector '[0.1, 0.2, ..., 0.9]' \
  --filter '{"source":{"$eq":"docs"}}' \
  -k 20 --include-metadata
```

### Pipe embeddings directly into queries
```bash
jq -c '.embedding' doc.json | pc index vector query -n my-index --vector - -k 10
```

### Bulk metadata update with preview
```bash
# Preview first
pc index vector update -n my-index \
  --filter '{"env":{"$eq":"staging"}}' \
  --metadata '{"env":"production"}' \
  --dry-run

# Apply
pc index vector update -n my-index \
  --filter '{"env":{"$eq":"staging"}}' \
  --metadata '{"env":"production"}'
```

### Backup and restore
```bash
# Snapshot before a migration
pc backup create -i my-index -n "pre-migration"

# Restore to a new index if something goes wrong
pc backup restore -i <backup-uuid> -n my-index-restored
```

### Automate in CI/CD
```bash
export PINECONE_CLIENT_ID="..."
export PINECONE_CLIENT_SECRET="..."
pc auth configure --client-id "$PINECONE_CLIENT_ID" --client-secret "$PINECONE_CLIENT_SECRET"
pc index vector upsert -n my-index --file ./vectors.jsonl --batch-size 1000
```

### Script against JSON output
```bash
# Get all index names as a list
pc index list -j | jq -r '.[] | .name'

# Check if an index exists before creating
if ! pc index describe -n my-index -j 2>/dev/null | jq -e '.name' > /dev/null; then
  pc index create -n my-index -d 1536 -m cosine -c aws -r us-east-1
fi
```

---

## Reference Files

- [Full command reference](references/command-reference.md) — all commands with flags and examples
- [Troubleshooting & best practices](references/troubleshooting.md)

## Documentation

- [CLI Quickstart](https://docs.pinecone.io/reference/cli/quickstart)
- [Command Reference](https://docs.pinecone.io/reference/cli/command-reference)
- [Authentication](https://docs.pinecone.io/reference/cli/authentication)
- [Target Context](https://docs.pinecone.io/reference/cli/target-context)
- [GitHub Releases](https://github.com/pinecone-io/cli/releases)
