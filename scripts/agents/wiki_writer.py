"""Deterministic wiki writer — no LLM. Upserts entity pages from extraction JSON."""
from __future__ import annotations

import difflib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

FUZZY_NAME_CUTOFF = 0.90

ENTITY_TYPE_TO_DIR: dict[str, str] = {
    "Person": "people",
    "Organization": "organizations",
    "Concept": "concepts",
    "Work": "works",
    "Method": "methods",
    "Product": "products",
    "Podcast": "podcasts",
    "Event": "_events",
    "Place": "_places",
}

EDGE_TYPE_TO_KEY: dict[str, str] = {
    "Hosts": "hosts",
    "AppearsOn": "appears_on",
    "WorksWith": "works_with",
    "AffiliatedWith": "affiliated_with",
    "Claims": "claims",
    "Recommends": "recommends",
    "Describes": "describes",
    "References": "references",
    "Sponsors": "sponsors",
    "RelatesTo": "relates_to",
}


def slugify(name: str) -> str:
    """Convert a display name to a URL-safe slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


_TIMESTAMP_RANGE = re.compile(r"^\s*([^-\u2013\u2014]+?)\s*[-\u2013\u2014].+$")
_TIMESTAMP_SECONDS = re.compile(r"^(\d+(?:\.\d+)?)\s*s?$")
_TIMESTAMP_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,]\d+)?$")


def canonical_timestamp(raw: Any) -> str:
    """Normalize an LLM-emitted timestamp to ``HH:MM:SS``.

    Accepts bare seconds (``3534`` / ``3534s``), clock format (``3:49``,
    ``58:54``, ``1:01:40``), and ranges (``1298s-1300s`` → start of range).
    Returns the original string unchanged if it doesn't parse — we'd rather
    preserve odd input than lose it.
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Range → take the first endpoint ("1298s-1300s" → "1298s")
    m = _TIMESTAMP_RANGE.match(text)
    if m:
        text = m.group(1).strip()

    seconds: float | None = None
    m = _TIMESTAMP_SECONDS.match(text)
    if m:
        seconds = float(m.group(1))
    else:
        m = _TIMESTAMP_CLOCK.match(text)
        if m:
            a, b, c = m.group(1), m.group(2), m.group(3)
            if c is not None:
                # H:M:S
                seconds = int(a) * 3600 + int(b) * 60 + int(c)
            else:
                # M:S (short form)
                seconds = int(a) * 60 + int(b)

    if seconds is None or seconds < 0:
        return str(raw).strip()
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def sanitize_slug(slug: str) -> str:
    """Normalize an LLM-provided slug.

    The extractor sometimes emits slugs with a directory prefix
    (``"people/elon-musk"``) or stray whitespace/case. Keep only the
    basename and re-slugify so a merge always writes to
    ``wiki/people/elon-musk.md`` and never ``wiki/people/people/...``.
    """
    if not slug:
        return ""
    if "/" in slug:
        slug = slug.rsplit("/", 1)[-1]
    return slugify(slug)


def load_page(path: Path) -> dict:
    """Load YAML front matter from a .md file. Returns empty dict if missing or unparseable."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def save_page(path: Path, front_matter: dict, body: str = "") -> None:
    """Write YAML front matter + markdown body to a .md file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_str = yaml.dump(
        front_matter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    path.write_text(f"---\n{fm_str}---\n\n{body}", encoding="utf-8")


def read_index(wiki_dir: Path) -> dict[str, dict]:
    """Parse _index.md into a lookup dict keyed by lowercase name and aliases.

    Returns: {lowercase_name: {"type": str, "file": str, "aliases": [str]}}
    """
    index_path = wiki_dir / "_index.md"
    if not index_path.exists():
        return {}
    result: dict[str, dict] = {}
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or line.startswith("| Name") or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        name, entity_type, file_path, aliases_str = parts[0], parts[1], parts[2], parts[3]
        aliases = [a.strip().lower() for a in aliases_str.split(",") if a.strip()]
        entry = {"type": entity_type.lower(), "file": file_path, "aliases": aliases}
        result[name.lower()] = entry
        for alias in aliases:
            result[alias] = entry
    return result


def _append_index_row(wiki_dir: Path, name: str, entity_type: str, file_path: str, aliases: list[str]) -> None:
    """Append a new row to _index.md."""
    index_path = wiki_dir / "_index.md"
    aliases_str = ", ".join(aliases) if aliases else ""
    row = f"| {name} | {entity_type.lower()} | {file_path} | {aliases_str} |\n"
    with index_path.open("a", encoding="utf-8") as f:
        f.write(row)


def _edge_key_for(
    entity: dict,
    edge: dict,
    index: dict | None = None,
) -> tuple[str, str]:
    """Return (edge_relationship_key, wikilink_target) for an edge from entity.

    When ``index`` is provided, resolve the target wikilink against it first
    so "Not On The High Street" re-uses the existing
    ``organizations/not-in-the-high-street`` page instead of creating a
    slug twin. Fuzzy matches are accepted at the same cutoff as page merges.
    """
    edge_key = EDGE_TYPE_TO_KEY.get(edge["type"], "relates_to")
    target_type = edge.get("to_type") or ""
    target_dir = ENTITY_TYPE_TO_DIR.get(target_type, "_unknown")
    target_name = edge.get("to_name") or ""

    if index and target_name and target_type:
        resolved = _find_existing_slug(target_name, target_type, index)
        if resolved:
            existing_slug = resolved[0].removesuffix(".md")
            return edge_key, f"[[{target_dir}/{existing_slug}]]"

    target_slug = slugify(target_name)
    return edge_key, f"[[{target_dir}/{target_slug}]]"


def _edge_is_duplicate(existing_edges: list[dict], new_edge_attrs: dict) -> bool:
    """Check if an edge with same (entity, episode, timestamp) already exists.

    Timestamp is part of the key so that two claims at different points in the
    same episode are preserved — only byte-for-byte re-runs collapse.
    """
    for ex in existing_edges:
        if (ex.get("entity") == new_edge_attrs.get("entity")
                and ex.get("episode") == new_edge_attrs.get("episode")
                and ex.get("timestamp") == new_edge_attrs.get("timestamp")):
            return True
    return False


def _entity_page_path(entity_type: str, slug: str, wiki_dir: Path) -> Path:
    type_dir = ENTITY_TYPE_TO_DIR.get(entity_type, "_unknown")
    return wiki_dir / type_dir / f"{slug}.md"


def _is_junk_person(entity: dict) -> bool:
    """Heuristic: drop single-token Person entities that look like
    unresolved speaker-label artifacts ("Dom", "Jack"). Any person with a
    multi-token name or substantive role attributes is kept.

    This fires when Stage 1 PREP couldn't resolve a speaker label — the LLM
    sees the raw "Dom:" prefix in the transcript and dutifully creates a
    Person entity named "Dom" that will never resolve to a real human.
    """
    if entity.get("type") != "Person":
        return False
    name = (entity.get("name") or "").strip()
    if not name or " " in name:  # multi-token → keep (full names are legit)
        return False
    attrs = entity.get("attributes") or {}
    if attrs.get("role_context") or attrs.get("expertise") or attrs.get("credentials"):
        return False
    return True


def _find_existing_slug(
    name: str,
    entity_type: str,
    index: dict,
) -> tuple[str, bool] | None:
    """Return (existing_slug, was_fuzzy) if an index entry of the same
    entity type matches ``name`` exactly (via canonical name or alias) or
    within FUZZY_NAME_CUTOFF ratio. Used to merge spelling variants like
    "Steven Bartlett" / "Stephen Bartlett" into a single page.
    """
    name_lower = name.lower().strip()
    type_lower = entity_type.lower()

    # Exact match (hits canonical name or any recorded alias)
    entry = index.get(name_lower)
    if entry and entry.get("type") == type_lower:
        return entry["file"].rsplit("/", 1)[-1], False

    # Fuzzy match — restrict candidates to same type to avoid cross-type collisions
    candidates = [k for k, e in index.items() if e.get("type") == type_lower]
    close = difflib.get_close_matches(
        name_lower, candidates, n=1, cutoff=FUZZY_NAME_CUTOFF
    )
    if close:
        return index[close[0]]["file"].rsplit("/", 1)[-1], True
    return None


_SOURCES_HEADER = "## Sources"


_PERSON_SOURCES_CACHE: dict[str, list[dict]] = {}


def _fetch_person_sources(name: str) -> list[dict]:
    """Return people.sources for the given name, empty list if missing.

    Memoized per process: stage0_enrich writes to people.sources before the
    wiki pipeline runs, so the table is stable for the duration of an
    extraction. This cuts the `merge_to_wiki` N-chunks × M-person-pages
    re-query storm down to one lookup per unique (lowercased) name.
    """
    key = name.strip().lower()
    if key in _PERSON_SOURCES_CACHE:
        return _PERSON_SOURCES_CACHE[key]
    from scripts.agents.db import fetch_one
    row = fetch_one(
        "SELECT sources FROM people WHERE lower(name) = %s LIMIT 1",
        (key,),
    )
    sources: list[dict] = []
    raw = (row or {}).get("sources")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, list):
        sources = raw
    _PERSON_SOURCES_CACHE[key] = sources
    return sources


def clear_person_sources_cache() -> None:
    """Drop memoized sources — call after stage0_enrich updates people.sources."""
    _PERSON_SOURCES_CACHE.clear()


def _render_sources_block(sources: list[dict]) -> str:
    """Render a `## Sources` markdown section from people.sources entries.

    Deduped by URL. Each line: ``- [title](url) — snippet`` (snippet truncated).
    """
    if not sources:
        return ""
    seen: set[str] = set()
    lines = [_SOURCES_HEADER]
    for s in sources:
        url = (s.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = (s.get("title") or url).strip()
        snippet = (s.get("snippet") or "").strip()
        line = f"- [{title}]({url})"
        if snippet:
            # Keep lines readable — truncate snippet aggressively
            short = snippet[:140].rsplit(" ", 1)[0] if len(snippet) > 140 else snippet
            line += f" — {short}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _upsert_sources_in_body(body: str, sources_block: str) -> str:
    """Replace an existing `## Sources` section with ``sources_block``, or
    append when not present. Empty ``sources_block`` leaves the body alone."""
    if not sources_block:
        return body
    idx = body.find(_SOURCES_HEADER)
    if idx == -1:
        sep = "\n\n" if body.strip() else ""
        return f"{body.rstrip()}{sep}{sources_block}".lstrip()
    return (body[:idx].rstrip() + "\n\n" + sources_block).lstrip()


def _merge_entity_page(
    entity: dict,
    edges_for_entity: list[dict],
    observations_for_entity: list[dict],
    wiki_dir: Path,
    youtube_id: str,
    index: dict,
) -> Path:
    """Upsert a single entity page. Returns the page path."""
    entity_type = entity["type"]
    name = entity["name"]
    attributes = entity.get("attributes") or {}

    # Prefer an existing page if this name (or a near variant) already
    # lives in the index. Fuzzy hits become aliases of the canonical page.
    resolved = _find_existing_slug(name, entity_type, index)
    if resolved:
        slug, was_fuzzy = resolved
        alias_to_add = name if was_fuzzy else None
    else:
        slug = sanitize_slug(entity.get("slug") or "") or slugify(name)
        alias_to_add = None

    page_path = _entity_page_path(entity_type, slug, wiki_dir)
    fm = load_page(page_path)

    if not fm:
        # New page — build front matter from scratch
        fm = {
            "type": entity_type.lower(),
            "name": name,
            "slug": slug,
            "aliases": [],
            "appearances": [],
            "relationships": {},
            "observations": [],
            "enriched": False,
            "created_at": str(date.today()),
            "updated_at": str(date.today()),
        }

    # Merge attributes (only fill in empty/missing fields)
    for key, value in attributes.items():
        if key and value and key not in fm:
            fm[key] = value

    # Record alt spelling as alias when we merged via fuzzy match
    if alias_to_add and alias_to_add != fm.get("name"):
        aliases = fm.setdefault("aliases", [])
        if alias_to_add not in aliases:
            aliases.append(alias_to_add)

    # Update updated_at
    fm["updated_at"] = str(date.today())

    # Merge edges into relationships
    rels = fm.setdefault("relationships", {})
    for edge in edges_for_entity:
        edge_key, wikilink = _edge_key_for(entity, edge, index=index)
        edge_attrs = dict(edge.get("attributes") or {})
        edge_attrs["entity"] = wikilink
        edge_attrs["episode"] = edge.get("episode", youtube_id)
        if "timestamp" in edge_attrs:
            edge_attrs["timestamp"] = canonical_timestamp(edge_attrs["timestamp"])
        existing = rels.setdefault(edge_key, [])
        if not _edge_is_duplicate(existing, edge_attrs):
            existing.append(edge_attrs)

    # Merge observations
    obs_list = fm.setdefault("observations", [])
    for obs in observations_for_entity:
        obs_entry = {
            "episode": obs.get("episode", youtube_id),
            "timestamp": canonical_timestamp(obs.get("timestamp", "")),
            "text": obs.get("text", ""),
        }
        # Dedup by text
        if not any(o.get("text") == obs_entry["text"] for o in obs_list):
            obs_list.append(obs_entry)

    # Preserve existing body if page already existed
    existing_body = ""
    if page_path.exists():
        text = page_path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) == 3:
            existing_body = parts[2].strip()

    # Render ## Sources section from stage0_enrich data (Person pages only)
    if entity_type == "Person":
        sources = _fetch_person_sources(fm.get("name") or name)
        block = _render_sources_block(sources)
        existing_body = _upsert_sources_in_body(existing_body, block)

    save_page(page_path, fm, existing_body)

    # Add to index if new; if this was a fuzzy merge, register the alias so
    # subsequent chunks in the same batch resolve to the same page.
    if name.lower() not in index:
        file_ref = f"{ENTITY_TYPE_TO_DIR.get(entity_type, '_unknown')}/{slug}"
        # Fuzzy merges reuse an existing page, so don't append a new index row
        if not alias_to_add:
            _append_index_row(wiki_dir, name, entity_type, file_ref, fm.get("aliases", []))
        index[name.lower()] = {
            "type": entity_type.lower(),
            "file": file_ref,
            "aliases": [],
        }

    return page_path


def merge_to_wiki(extraction: dict, youtube_id: str, wiki_dir: Path) -> list[Path]:
    """Apply extraction JSON to wiki pages. Returns list of touched page paths."""
    entities = extraction.get("entities") or []
    edges = extraction.get("edges") or []
    observations = extraction.get("observations") or []

    # Drop junk single-token Person entities + any edges/observations that
    # reference them (they're unresolved speaker-label artifacts).
    junk_names = {e.get("name") for e in entities if _is_junk_person(e)}
    if junk_names:
        entities = [e for e in entities if e.get("name") not in junk_names]
        edges = [
            e for e in edges
            if e.get("from_name") not in junk_names
            and e.get("to_name") not in junk_names
        ]
        observations = [
            o for o in observations if o.get("entity_name") not in junk_names
        ]

    # Load current index once
    index = read_index(wiki_dir)

    # Group edges and observations by source entity name
    edges_by_entity: dict[str, list] = {}
    for edge in edges:
        edges_by_entity.setdefault(edge.get("from_name", ""), []).append(edge)

    obs_by_entity: dict[str, list] = {}
    for obs in observations:
        obs_by_entity.setdefault(obs.get("entity_name", ""), []).append(obs)

    touched: list[Path] = []
    for entity in entities:
        name = entity.get("name", "")
        path = _merge_entity_page(
            entity=entity,
            edges_for_entity=edges_by_entity.get(name, []),
            observations_for_entity=obs_by_entity.get(name, []),
            wiki_dir=wiki_dir,
            youtube_id=youtube_id,
            index=index,
        )
        touched.append(path)

    return touched
