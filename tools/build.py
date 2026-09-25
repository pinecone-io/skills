#!/usr/bin/env python3
# Pinned exactly, not floating. These install at CI job time in a job that holds a
# write token for the plugin repos, so a compromised release would run there. The
# same floating-lower-bound habit is what let pinecone 9 break every skill script.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml==6.0.3",
#   "typer==0.27.1",
# ]
# ///
"""Render skills/ into dist/<target>/ using a target manifest.

Replaces the previous arrangement, where each target repo ran its own agent to
rewrite skills on arrival — three targets, three agents, three answers to the
same question. This is a pure function: same inputs, same bytes, every run.

    uv run tools/build.py --all
    uv run tools/build.py --target claude-code
    uv run tools/build.py --all --check    # verify only, write nothing

See targets/README.md for the manifest schema and the transform rules.
"""

from __future__ import annotations

import ast
import filecmp
import re
import shutil
from pathlib import Path
from typing import Any

import typer
import yaml

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO / "skills"
TARGETS_DIR = REPO / "targets"
DIST_DIR = REPO / "dist"

BASE_PREFIX = "pinecone-"
NEUTRAL_SOURCE_TAG = "pinecone_skills"

# The assistant create script stamps this metadata key on every assistant it makes.
# It is a second per-target value with the same shape as source_tag, and it was
# missed for months: base hardcoded `claude-code-plugin`, so a sync would have
# labelled Cursor-created assistants as Claude Code.
IDE_SOURCE_KEY = "agentic-ide-source"
NEUTRAL_IDE_SOURCE = "pinecone-skills"

# Snippet markers. `<<name>>` and not `{{ name }}`: pinecone-n8n/SKILL.md is full of
# real n8n expressions like `={{ $json.urls }}`, and a marker that looks like one
# would confuse both the build and whoever edits that file next. `<<` appears
# nowhere in base.
SNIPPET_RE = re.compile(r"<<([a-z][a-z0-9_]*)>>")

# Frontmatter keys, in the order the build must emit them. `allowed-tools` comes
# from the manifest and is appended last; the rest pass through from base.
FRONTMATTER_ORDER = ["name", "description", "argument-hint", "allowed-tools"]


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #

def load_manifest(target: str) -> dict[str, Any]:
    path = TARGETS_DIR / f"{target}.yaml"
    if not path.exists():
        raise typer.BadParameter(f"no manifest at {path.relative_to(REPO)}")
    m = yaml.safe_load(path.read_text())
    for key in ("repo", "skills_path", "dir_name", "skill_name", "cross_reference",
                "source_tag", "ide_source", "include"):
        if key not in m:
            raise ValueError(f"{target}.yaml is missing required key: {key}")
    m.setdefault("frontmatter", {}) or m.__setitem__("frontmatter", m.get("frontmatter") or {})
    unknown = set(m["frontmatter"]) - set(m["include"])
    if unknown:
        raise ValueError(f"{target}.yaml has frontmatter for non-included slugs: {sorted(unknown)}")
    return m


def available_targets() -> list[str]:
    return sorted(p.stem for p in TARGETS_DIR.glob("*.yaml"))


# --------------------------------------------------------------------------- #
# transforms — each is a pure str -> str
# --------------------------------------------------------------------------- #

def slug_alternation(slugs: list[str]) -> str:
    """Longest slug first, so `full-text-search` wins over any shorter alternative."""
    return "|".join(re.escape(s) for s in sorted(slugs, key=len, reverse=True))


def cross_reference_pattern(slugs: list[str]) -> re.Pattern[str]:
    """Match `pinecone-<slug>` only for known slugs, and only when it stands alone.

    The slug list is the first guard: a blanket `pinecone-` substitution would eat
    `pinecone-io` URLs and index names like `pinecone-fts-index`.

    The lookarounds are the second, and they are not optional. `\\b` is too weak
    here because a hyphen is a word boundary, so `\\bpinecone-assistant\\b` matches
    *inside* `@pinecone-database/n8n-nodes-pinecone-assistant` and rewrites an npm
    package name to `n8n-nodes-pinecone:assistant`. Rejecting an adjacent `-` on
    either side fixes that, and also protects trailing forms like
    `pinecone-cli-tool`.

    An adjacent `/` is rejected for a different reason: that is a path segment, not
    prose, and paths follow `dir_name` rather than `cross_reference`. See
    `rewrite_skill_paths`.
    """
    return re.compile(rf"(?<![\w/-]){re.escape(BASE_PREFIX)}(?:{slug_alternation(slugs)})(?![\w/-])")


def skill_path_pattern(slugs: list[str]) -> re.Pattern[str]:
    """Match `pinecone-<slug>/` — a skill directory used as a path segment."""
    return re.compile(rf"(?<![\w-]){re.escape(BASE_PREFIX)}(?:{slug_alternation(slugs)})(?=/)")


def rewrite_skill_paths(text: str, manifest: dict[str, Any]) -> str:
    """Rewrite skill directories that appear inside filesystem paths.

    `pinecone-quickstart/SKILL.md` tells the user to run
    `uv run ../pinecone-assistant/scripts/create.py`. That is a real path to a
    sibling directory, so it has to track `dir_name`: the Claude plugin renames the
    directory to `assistant/`, and a build that emitted `../pinecone-assistant/`
    there would hand the user a path that does not exist. Feeding it through
    `cross_reference` instead is worse — it produced `../pinecone:assistant/`.
    """
    def repl(match: re.Match[str]) -> str:
        return manifest["dir_name"].format(slug=match.group(0)[len(BASE_PREFIX):])

    return skill_path_pattern(manifest["include"]).sub(repl, text)


def rewrite_cross_references(text: str, manifest: dict[str, Any]) -> str:
    """Rewrite prose references to other skills. Paths are handled first and are
    excluded by the pattern's lookarounds, so the two rules cannot both fire."""
    text = rewrite_skill_paths(text, manifest)
    template = manifest["cross_reference"]

    def repl(match: re.Match[str]) -> str:
        return template.format(slug=match.group(0)[len(BASE_PREFIX):])

    return cross_reference_pattern(manifest["include"]).sub(repl, text)


def rewrite_source_tag(text: str, manifest: dict[str, Any]) -> str:
    """Retarget `pinecone_skills:<x>` to `<target_tag>:<x>` inside .py files."""
    return re.sub(
        rf"\b{re.escape(NEUTRAL_SOURCE_TAG)}:",
        f"{manifest['source_tag']}:",
        text,
    )


IDE_SOURCE_RE = re.compile(rf'("{re.escape(IDE_SOURCE_KEY)}"\s*:\s*")([^"]*)(")')


def rewrite_ide_source(text: str, manifest: dict[str, Any], path: Path) -> str:
    """Retarget the `agentic-ide-source` metadata value inside .py files.

    Strict on purpose. Base must hold the neutral value, so anything else means a
    target name has been hardcoded into shared source again. Silently overwriting
    it would hide the very drift this rule exists to stop.
    """
    def repl(match: re.Match[str]) -> str:
        found = match.group(2)
        if found not in (NEUTRAL_IDE_SOURCE, manifest["ide_source"]):
            raise ValueError(
                f"{path}: {IDE_SOURCE_KEY} is {found!r}; base must use "
                f"{NEUTRAL_IDE_SOURCE!r} so each target can set its own"
            )
        return match.group(1) + manifest["ide_source"] + match.group(3)

    return IDE_SOURCE_RE.sub(repl, text)


def fill_snippets(text: str, manifest: dict[str, Any], path: Path) -> str:
    """Replace `<<name>>` with the target's wording for that name.

    This is the declared replacement for the agent that used to rewrite skills
    inside each plugin repo. Some things really do differ per plugin — Cursor reads
    `.env` through its own MCP config, Claude Code has working slash commands — and
    base cannot state both. An agent inferred the difference and gave a slightly
    different answer every run. A snippet states it once, in a file you can review.

    Undefined names are a hard error. A skill published with `<<api_key_setup>>`
    sitting in the text would be worse than either wording.
    """
    snippets = manifest.get("snippets") or {}

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in snippets:
            raise ValueError(
                f"{path}: no snippet {name!r} for this target. Define it in "
                f"targets/*.yaml for every target, or remove the marker from base."
            )
        return str(snippets[name]).strip()

    return SNIPPET_RE.sub(repl, text)


def split_frontmatter(text: str, path: Path) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Preserves value strings verbatim."""
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: SKILL.md must open with a --- frontmatter block")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ValueError(f"{path}: unterminated frontmatter block")
    block, body = text[4:end + 1], text[end + 5:]

    fm: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        if ": " not in line and not line.endswith(":"):
            raise ValueError(f"{path}: cannot parse frontmatter line: {line!r}")
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm, body


def render_frontmatter(fm: dict[str, str]) -> str:
    """Emit keys in FRONTMATTER_ORDER; anything unrecognised is an error rather
    than silently dropped."""
    unknown = [k for k in fm if k not in FRONTMATTER_ORDER]
    if unknown:
        raise ValueError(f"unhandled frontmatter keys: {unknown} (add them to FRONTMATTER_ORDER)")
    lines = [f"{k}: {fm[k]}" for k in FRONTMATTER_ORDER if k in fm]
    return "---\n" + "\n".join(lines) + "\n---\n"


def render_skill_md(text: str, slug: str, manifest: dict[str, Any], path: Path) -> str:
    fm, body = split_frontmatter(text, path)

    expected = f"{BASE_PREFIX}{slug}"
    if fm.get("name") != expected:
        raise ValueError(f"{path}: name is {fm.get('name')!r}, expected {expected!r}")
    fm["name"] = manifest["skill_name"].format(slug=slug)

    extra = (manifest["frontmatter"].get(slug) or {})
    for key, value in extra.items():
        fm[key] = value

    # Cross-references appear in the description as well as the body.
    if "description" in fm:
        fm["description"] = rewrite_cross_references(fm["description"], manifest)
    return render_frontmatter(fm) + rewrite_cross_references(body, manifest)


def render_file(rel: Path, text: str, slug: str, manifest: dict[str, Any], path: Path) -> str:
    # Snippets first, deliberately. Their text can contain skill names and paths, so
    # filling them before the other rules run means snippet content passes through
    # the same guards as base content instead of going around them.
    text = fill_snippets(text, manifest, path)
    if rel.name == "SKILL.md":
        return render_skill_md(text, slug, manifest, path)
    if rel.suffix == ".py":
        return rewrite_ide_source(rewrite_source_tag(text, manifest), manifest, path)
    if rel.suffix == ".md":
        return rewrite_cross_references(text, manifest)
    return text


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #

def build_target(target: str, out_root: Path | None = None) -> tuple[Path, int]:
    """Render one target. Returns (output dir, files written)."""
    manifest = load_manifest(target)
    out = (out_root or DIST_DIR) / target / manifest["skills_path"]
    if out.parent.exists():
        shutil.rmtree(out.parent)
    out.mkdir(parents=True)

    written = 0
    for slug in manifest["include"]:
        src = SKILLS_DIR / f"{BASE_PREFIX}{slug}"
        if not src.is_dir():
            raise ValueError(f"{target}: include lists {slug!r} but {src.relative_to(REPO)} does not exist")
        dest_dir = out / manifest["dir_name"].format(slug=slug)

        for path in sorted(src.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(src)
            dest = dest_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = path.read_text()
            except UnicodeDecodeError:          # binary asset: copy through
                shutil.copy2(path, dest)
                written += 1
                continue
            dest.write_text(render_file(rel, text, slug, manifest, path))
            written += 1
    return out.parent, written


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #

def permitted_line_changes(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """(marker in base, value in rendered) pairs the identity check tolerates.

    Every per-target scalar belongs here. Leaving one out makes the identity check
    fail on a legitimate rewrite; adding one loosely makes it blind to a real
    change. Keep it to exact neutral markers.
    """
    return [
        (NEUTRAL_SOURCE_TAG, manifest["source_tag"]),
        (NEUTRAL_IDE_SOURCE, manifest["ide_source"]),
    ]


def check_identity_target(target: str, out_root: Path | None = None) -> list[str]:
    """For a target whose dir_name and skill_name equal base, rendered output must
    be byte-identical to base except for the per-target scalars above.

    This is the cheapest possible regression test for such a target — it replaces
    a paid eval run with an exact comparison.
    """
    manifest = load_manifest(target)
    if manifest["dir_name"] != f"{BASE_PREFIX}{{slug}}" or manifest["skill_name"] != f"{BASE_PREFIX}{{slug}}":
        return []                                # not an identity target; nothing to assert
    out = (out_root or DIST_DIR) / target / manifest["skills_path"]
    problems: list[str] = []
    for slug in manifest["include"]:
        base = SKILLS_DIR / f"{BASE_PREFIX}{slug}"
        rendered = out / f"{BASE_PREFIX}{slug}"
        for path in sorted(base.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(base)
            other = rendered / rel
            if not other.exists():
                problems.append(f"{target}: missing {rel} under {slug}")
                continue
            # Fill snippets on the base side too. Snippets are a declared per-target
            # difference, and a multi-line one would otherwise trip the line-count
            # comparison below. What this still asserts is the valuable part: no
            # *other* rule changed anything for an identity target.
            a = fill_snippets(path.read_text(), manifest, path).splitlines()
            b = other.read_text().splitlines()
            if len(a) != len(b):
                problems.append(f"{target}: line count differs for {slug}/{rel}")
                continue
            permitted = permitted_line_changes(manifest)
            for i, (la, lb) in enumerate(zip(a, b), 1):
                if la == lb:
                    continue
                if any(marker in la and value in lb for marker, value in permitted):
                    continue                     # a declared per-target scalar
                problems.append(f"{target}: unexpected change at {slug}/{rel}:{i}\n    - {la}\n    + {lb}")
    return problems


def check_no_neutral_tags(target: str, out_root: Path | None = None) -> list[str]:
    """No rendered output may still carry a neutral per-target marker.

    Catches the case where base grows a new site the rewrite rules do not reach —
    a new script, or the same field written with different spacing.
    """
    manifest = load_manifest(target)
    out = (out_root or DIST_DIR) / target / manifest["skills_path"]
    problems: list[str] = []
    for p in sorted(out.rglob("*.py")):
        text = p.read_text()
        if f"{NEUTRAL_SOURCE_TAG}:" in text:
            problems.append(f"{target}: {p.relative_to(out)} still contains {NEUTRAL_SOURCE_TAG}:")
        if NEUTRAL_IDE_SOURCE in text:
            problems.append(f"{target}: {p.relative_to(out)} still contains {NEUTRAL_IDE_SOURCE}")
    return problems


def check_python_syntax(target: str, out_root: Path | None = None) -> list[str]:
    """Every rendered .py file must parse.

    Snippets land inside string literals, so a snippet that ends with a quote next
    to a closing triple quote produces a file that cannot be imported. Nothing else
    in the build would notice: the bytes look fine and only Python objects. Users
    would find it. This check finds it first.
    """
    manifest = load_manifest(target)
    out = (out_root or DIST_DIR) / target / manifest["skills_path"]
    problems = []
    for path in sorted(out.rglob("*.py")):
        try:
            ast.parse(path.read_text())
        except SyntaxError as exc:
            problems.append(f"{target}: {path.relative_to(out)} does not parse — {exc}")
    return problems


def check_snippets(target: str) -> list[str]:
    """Snippet definitions and markers must agree, in both directions.

    Missing definitions already fail during render. This catches the quieter half:
    a snippet defined in a manifest that base no longer references. Left unchecked,
    stale wording sits in the manifest looking authoritative for months.
    """
    manifest = load_manifest(target)
    defined = set(manifest.get("snippets") or {})
    referenced: set[str] = set()
    for slug in manifest["include"]:
        src = SKILLS_DIR / f"{BASE_PREFIX}{slug}"
        for path in sorted(src.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            try:
                referenced |= set(SNIPPET_RE.findall(path.read_text()))
            except UnicodeDecodeError:
                continue

    problems = [
        f"{target}: snippet {name!r} is defined but no included skill uses <<{name}>>"
        for name in sorted(defined - referenced)
    ]
    problems += [
        f"{target}: base uses <<{name}>> but targets/{target}.yaml does not define it"
        for name in sorted(referenced - defined)
    ]
    return problems


def check_idempotent(target: str, tmp_root: Path) -> list[str]:
    """Building twice must produce identical bytes."""
    a, _ = build_target(target, tmp_root / "a")
    b, _ = build_target(target, tmp_root / "b")
    diff = filecmp.dircmp(a, b)

    def walk(d: filecmp.dircmp) -> list[str]:
        out = [f"{target}: not idempotent — {n}" for n in d.diff_files + d.left_only + d.right_only]
        for sub in d.subdirs.values():
            out += walk(sub)
        return out

    return walk(diff)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

@app.command()
def main(
    target: str = typer.Option("", "--target", "-t", help="Target manifest name, e.g. claude-code."),
    all_targets: bool = typer.Option(False, "--all", help="Build every manifest in targets/."),
    check: bool = typer.Option(False, "--check", help="Run the checks; write nothing permanent."),
    out: str = typer.Option("", "--out", help="Output root. Defaults to dist/."),
):
    """Render skills/ into dist/<target>/ from a target manifest."""
    if not target and not all_targets:
        raise typer.BadParameter("pass --target NAME or --all")
    targets = available_targets() if all_targets else [target]
    out_root = Path(out).resolve() if out else None

    problems: list[str] = []
    for t in targets:
        path, n = build_target(t, out_root)
        typer.echo(f"built {t}: {n} files -> {path.relative_to(REPO) if not out_root else path}")
        problems += check_no_neutral_tags(t, out_root)
        problems += check_identity_target(t, out_root)
        problems += check_snippets(t)
        problems += check_python_syntax(t, out_root)
        if check:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                problems += check_idempotent(t, Path(tmp))

    if problems:
        typer.echo("\nFAILED:")
        for p in problems:
            typer.echo(f"  {p}")
        raise typer.Exit(1)
    typer.echo("all checks passed")


if __name__ == "__main__":
    app()
