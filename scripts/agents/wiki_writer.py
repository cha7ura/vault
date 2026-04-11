"""Deterministic wiki writer — no LLM. Upserts entity pages from extraction JSON."""
from __future__ import annotations

import difflib
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


def _edge_key_for(entity: dict, edge: dict) -> tuple[str, str]:
    """Return (edge_relationship_key, wikilink_target) for an edge from entity."""
    edge_key = EDGE_TYPE_TO_KEY.get(edge["type"], "relates_to")
    target_dir = ENTITY_TYPE_TO_DIR.get(edge["to_type"], "_unknown")
    target_slug = slugify(edge["to_name"])
    wikilink = f"[[{target_dir}/{target_slug}]]"
    return edge_key, wikilink


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
        edge_key, wikilink = _edge_key_for(entity, edge)
        edge_attrs = dict(edge.get("attributes") or {})
        edge_attrs["entity"] = wikilink
        edge_attrs["episode"] = edge.get("episode", youtube_id)
        existing = rels.setdefault(edge_key, [])
        if not _edge_is_duplicate(existing, edge_attrs):
            existing.append(edge_attrs)

    # Merge observations
    obs_list = fm.setdefault("observations", [])
    for obs in observations_for_entity:
        obs_entry = {
            "episode": obs.get("episode", youtube_id),
            "timestamp": obs.get("timestamp", ""),
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

    save_page(page_path, fm, existing_body)

    # Add to index if new; if this was a fuzzy merge, register the alias so
    # subsequent chunks in the same batch resolve to the same page.
    if name.lower() not in index:
        file_ref = f"{ENTITY_TYPE_TO_DIR.get(entity_type, '_unknown')}/{slug}"
        if alias_to_add:
            # Fuzzy-merged into an existing page — point this spelling at it
            index[name.lower()] = {
                "type": entity_type.lower(),
                "file": file_ref,
                "aliases": [],
            }
        else:
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
