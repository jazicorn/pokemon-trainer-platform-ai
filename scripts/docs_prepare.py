#!/usr/bin/env python3
"""Mirror this repo's markdown into web/docs-site/src/content/docs/ (ROADMAP.md Phase 10).

Astro/Starlight (like the MkDocs setup it replaced) can only render content that lives
inside its own project — it doesn't reach outside web/docs-site/ any more than MkDocs
reached outside docs_dir. So this script is the direct successor to the old
`make docs-prepare` `cp` lines: it copies README.md, both roadmap files, ARCHITECTURE.md,
HISTORY.md, CHANGELOG.md, and everything under docs/ into web/docs-site/src/content/docs/,
adding the Starlight frontmatter (title, and a `pokemonType` badge for pages that map to one
of the eight type tokens) that plain markdown files don't carry on their own, and rewriting
internal links to match the new destination paths.

Generated output is gitignored (see .gitignore) — same "one source of truth" reasoning as
before. The one hand-authored exception is src/content/docs/index.mdx (the home page hub),
which this script never touches.

Usage:
    uv run python scripts/docs_prepare.py
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_SRC = REPO_ROOT / "docs"
DEST_ROOT = REPO_ROOT / "web" / "docs-site" / "src" / "content" / "docs"

# Type-token mapping (see ROADMAP.md Phase 10). Checked by destination-path prefix, first
# match wins. Kept here instead of per-file frontmatter so the mapping stays in one place.
TYPE_BY_PREFIX: list[tuple[str, str]] = [
    ("onboarding/", "grass"),
    ("getting-started", "grass"),
    ("walkthrough-cli/phase-05", "psychic"),
    ("walkthrough-cli/phase-06", "electric"),
    ("walkthrough-cli/phase-07", "electric"),
    ("walkthrough-cli/phase-08", "dark"),
    ("walkthrough-cli/phase-09", "dragon"),
    ("walkthrough-cli/phase-10", "dragon"),
    ("walkthrough-cli/phase-13", "fighting"),
    ("reference/market-trends", "electric"),
    ("reference/eval-results", "fighting"),
    ("reference/1password-setup", "dark"),
    ("reference/platform-db", "dark"),
    ("reference/", "steel"),
    ("troubleshooting/", "fire"),
    ("architecture", "dragon"),
    ("roadmap/", "electric"),
]


@dataclass(frozen=True)
class Doc:
    source: Path  # absolute path to the source markdown file
    dest_slug: str  # destination path relative to DEST_ROOT, no extension (e.g. "reference/testing")
    title: str | None = None  # override the title instead of extracting the first H1
    strip_through: str | None = None  # for README.md: drop everything before this substring
    intro: str | None = None  # manually-authored lead paragraph, inserted after frontmatter


README_TAGLINE = (
    "A hierarchical multi-agent AI advisor for Pokémon trainers — five specialized agents "
    "collaborate on trade evaluation, market forecasting, legitimacy checks, battle viability, "
    "and Pokédex knowledge via RAG."
)

DOCS: list[Doc] = [
    Doc(
        REPO_ROOT / "README.md",
        "overview",
        title="Overview",
        strip_through="## \U0001f680 The Tech Stack",
        intro=README_TAGLINE,
    ),
    Doc(DOCS_SRC / "GETTING_STARTED.md", "getting-started"),
    Doc(REPO_ROOT / "ARCHITECTURE.md", "architecture"),
    Doc(REPO_ROOT / "ROADMAP.md", "roadmap/web-api", title="Web API (Phases 1-16)"),
    Doc(REPO_ROOT / "ROADMAP_PLATFORM.md", "roadmap/platform", title="Platform, Launch & Growth (Phases 17-29)"),
    Doc(REPO_ROOT / "HISTORY.md", "history"),
    Doc(REPO_ROOT / "CHANGELOG.md", "changelog"),
    Doc(DOCS_SRC / "1PASSWORD.md", "reference/1password-setup", title="1Password Setup"),
    Doc(DOCS_SRC / "ARIZE_PHOENIX_SETUP.md", "reference/arize-phoenix-setup"),
    Doc(DOCS_SRC / "DEPLOYMENT.md", "reference/deployment"),
]

for _dir, _dest in [
    ("ONBOARDING", "onboarding"),
    ("REFERENCE", "reference"),
    ("TROUBLESHOOTING", "troubleshooting"),
    ("WALKTHROUGH_CLI", "walkthrough-cli"),
]:
    for path in sorted((DOCS_SRC / _dir).glob("*.md")):
        stem = path.stem.lower()
        if stem == "phases_overview":
            # Sort before phase-01..14 in Starlight's alphabetical sidebar autogenerate —
            # "phases_overview" would otherwise land after "phase-0X" (hyphen < 's').
            stem = "00-phases-overview"
        DOCS.append(Doc(path, f"{_dest}/{stem}"))

# repo-relative source path -> new site route, for rewriting cross-references between docs.
LINK_MAP: dict[str, str] = {}
for doc in DOCS:
    try:
        key = doc.source.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        continue
    LINK_MAP[key] = f"/{doc.dest_slug}/"
# A few extra spellings the same files are referenced by across the corpus.
LINK_MAP["docs/1PASSWORD.md"] = "/reference/1password-setup/"
LINK_MAP["README.md"] = "/overview/"

H1_MD = re.compile(r"^#\s+(.+?)\s*$")
H1_HTML = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
LINK_TARGET = re.compile(r"(\]\()([^)\s]+)(\)|(?=\s))")
TAG_STRIP = re.compile(r"<[^>]+>")


def resolve_link(source: Path, target: str) -> str | None:
    """Resolve a markdown link target relative to `source`'s repo path; look it up in LINK_MAP."""
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return None
    clean = target.split("#", 1)[0]
    if not clean or not clean.endswith(".md"):
        return None
    resolved = (source.parent / clean).resolve()
    try:
        key = resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None
    return LINK_MAP.get(key)


def rewrite_links(source: Path, body: str) -> str:
    def _sub(m: re.Match[str]) -> str:
        new_target = resolve_link(source, m.group(2))
        return f"{m.group(1)}{new_target}{m.group(3)}" if new_target else m.group(0)

    return LINK_TARGET.sub(_sub, body)


def extract_title(text: str) -> tuple[str, str]:
    """Pull the first H1 (markdown or raw HTML) out of `text`; return (title, remaining_body)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if m := H1_MD.match(line):
            del lines[i]
            if i < len(lines) and not lines[i].strip():
                del lines[i]
            return m.group(1), "\n".join(lines)
        if m := H1_HTML.search(line):
            del lines[i]
            if i < len(lines) and not lines[i].strip():
                del lines[i]
            return TAG_STRIP.sub("", m.group(1)).strip(), "\n".join(lines)
    return "Untitled", text


def yaml_escape(value: str) -> str:
    return value.replace('"', '\\"')


def pokemon_type_for(slug: str) -> str | None:
    for prefix, ptype in TYPE_BY_PREFIX:
        if slug.startswith(prefix) or slug == prefix.rstrip("/"):
            return ptype
    return None


def build(doc: Doc) -> None:
    raw = doc.source.read_text(encoding="utf-8")
    if doc.strip_through:
        idx = raw.find(doc.strip_through)
        if idx != -1:
            raw = raw[idx:]
    extracted_title, body = extract_title(raw)
    title = doc.title or extracted_title
    body = rewrite_links(doc.source, body).strip() + "\n"

    frontmatter = [f'title: "{yaml_escape(title)}"']
    if doc.intro:
        frontmatter.append(f'description: "{yaml_escape(doc.intro)}"')
    ptype = pokemon_type_for(doc.dest_slug)
    if ptype:
        frontmatter.append(f"pokemonType: {ptype}")
    if doc.intro:
        body = f"{doc.intro}\n\n{body}"

    dest = DEST_ROOT / f"{doc.dest_slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("---\n" + "\n".join(frontmatter) + "\n---\n\n" + body, encoding="utf-8")


def main() -> None:
    # Clear everything generated last time except the hand-authored home page.
    for path in DEST_ROOT.iterdir():
        if path.name == "index.mdx":
            continue
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    for doc in DOCS:
        build(doc)

    print(f"Prepared {len(DOCS)} pages into {DEST_ROOT.relative_to(REPO_ROOT)}/")


if __name__ == "__main__":
    main()
