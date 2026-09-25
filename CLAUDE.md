# Skills Repo — Authoring Guidelines

This is the **base skills repo** and the only place skills are authored. Skills here must work across any agent environment (Claude Code, Cursor, etc.).

Plugin repos receive generated output. `tools/build.py` renders this tree per target using the manifests in `targets/`, and the sync workflow opens a pull request against each plugin repo. Nothing rewrites skills after they leave here, so what you write is what ships. Where a target genuinely needs different wording, base leaves a `<<marker>>` and each file in `targets/` supplies its own text — see `targets/README.md`.

## Generalization Rules

**No IDE-specific tool calls in base.** Don't name `AskUserQuestion` or any other tool that isn't universally available. Write plain prose: "ask the user which they prefer."

**Where a tool really is the right answer for one target, use a snippet instead of dropping the idea.** Base leaves a `<<marker>>`; each file in `targets/` supplies its own wording. That is how `AskUserQuestion` reaches the Claude Code plugin while Cursor gets prose — see `targets/README.md` → Snippets. Earlier the rule was a flat ban, which quietly cost the Claude plugin a working feature at 15 sites.

Add a snippet only where the targets truly differ. If one wording is right everywhere, it belongs in base.

**Never assume `PINECONE_API_KEY` is inherited.** Always check first. If not set:
- Tell the user to `export PINECONE_API_KEY=...` (terminal envs)
- Or create a `.env` file and run scripts with `uv run --env-file .env scripts/...` (IDE envs that don't inherit shell vars)

**MCP-dependent skills must say so.** If a skill requires MCP, state it in the description and fail fast with a helpful message if tools aren't available.

**No IDE-specific language.** Avoid phrases like "Claude Code console" or references to specific IDE UI.

**No fake API key literals.** Never write `pcsk_...` or similar patterns — use `your-key` as a placeholder. Security linters will flag fake key patterns.

## Linting

Run from `../tools/` (one directory up):

```bash
uv run ../tools/check-skills.py --skills-dir skills/
uv run ../tools/check-source-tags.py --dir .
uv run ../tools/check-links.py --skills-dir skills/
```
