# Pinecone CLI — Troubleshooting & Best Practices

## Troubleshooting

### Authentication Issues

If you cannot successfully authenticate through the pc login flow with json activated, please inform the user to:
- ensure to click the authetication link when prompted
- attempt to login themselves outside of an agentic session, then activate the session
- set an API key of PINECONE_API_KEY environment variable, before starting the agentic session.


**"Not authenticated" or "Invalid credentials"**
```bash
pc auth status
pc logout
pc login
pc target -o "my-org" -p "my-project"
```

**Service account can't access resources**
```bash
pc target --show   # Verify correct project is targeted
```

### API Key Issues

**API key not working**
```bash
pc config get-api-key   # Verify key is set
# API keys are scoped to org + project — get a new one if needed
pc api-key create -n "new-key" --store
```

### API Keys and Shell Environments

**`PINECONE_API_KEY` not available after exporting it**

In agent environments (Claude Code, Cursor, etc.), each shell command may run in a separate process. An `export PINECONE_API_KEY=...` in one command may not be available in the next. There are two ways to handle this:

1. **Export before starting the session** — run `export PINECONE_API_KEY="your-key"` in your terminal before launching the agent. The variable will be inherited by all child processes.

2. **Write to a `.env` file** — if you need to create a key mid-session, write it to `.env` and use `--env-file` when running scripts:
   ```bash
   pc api-key create --name my-key --json | jq -r '"PINECONE_API_KEY=" + .value' > .env
   uv run --env-file .env scripts/...
   ```

> **Important:** Add `.env` to your `.gitignore` to avoid committing API keys to your repository.

**CLI works but scripts don't**

The CLI stores its own auth token on disk (via `pc login`), so `pc` commands work across shell invocations. But Python/Node scripts using the Pinecone SDK read from `PINECONE_API_KEY`, which is a separate credential. Authenticating the CLI does not set this variable — you need to create and provide an API key separately.

### Target Context Issues

**"Project not found" or "Organization not found"**
```bash
pc target --show
pc target --clear
pc target -o "my-org" -p "my-project"
```

### Index Issues

**Index operations failing**
```bash
pc index describe -n my-index
# "Initializing" → wait and retry
# "Terminating" → recreate it
```

**Can't delete index**
```bash
# Check if deletion protection is on
pc index describe -n my-index
pc index configure -n my-index --deletion-protection disabled
pc index delete -n my-index
```

### Vector Upload Issues

**Upsert fails with dimension mismatch**
```bash
pc index describe -n my-index   # Check configured dimension
# Ensure all vectors have exactly that many values
```

**Large file upload is slow**
```bash
# Use max batch size
pc index vector upsert -n my-index --file ./large.json --batch-size 1000

# Or split JSONL and loop
split -l 10000 large.jsonl chunk-
for file in chunk-*; do
  pc index vector upsert -n my-index --file "$file"
done
```

### Query Issues

**Query returns no results**
```bash
pc index stats -n my-index          # Check if data exists
pc index namespace list -n my-index # Verify namespace
# Filters use MongoDB query syntax — double-check filter format
```

### Backup Issues

**Backup creation fails**
```bash
pc index describe -n my-index
# Backups are only supported for serverless indexes in "Ready" state
```

**Can't find backup ID**
```bash
pc backup list --index-name my-index
# Use the UUID (e.g. c84725e5-...) not the name for restore/delete
```

---

## Best Practices

### Use the right auth method
- **Interactive dev**: `pc login`
- **CI/CD pipelines**: service accounts
- **Quick testing**: `pc api-key create -n "my-key" --store`

### Check status before operating
```bash
pc auth status
pc target --show
pc index describe -n my-index
```

### Use JSON output for scripts
```bash
pc index list -j | jq -r '.[] | .name'
```

### Preview destructive operations
```bash
pc index vector update -n my-index \
  --filter '{"genre":{"$eq":"old"}}' \
  --metadata '{"genre":"new"}' \
  --dry-run
```

### Protect production indexes
```bash
pc index create -n prod-index -d 1536 -m cosine -c aws -r us-east-1 \
  --deletion-protection enabled
```

### Automate backups
```bash
pc backup create -i my-index -n "daily-backup-$(date +%Y%m%d)"
```
