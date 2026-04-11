import tempfile
from pathlib import Path
import yaml
import pytest
from scripts.agents.wiki_writer import (
    slugify,
    sanitize_slug,
    load_page,
    save_page,
    read_index,
    merge_to_wiki,
)


def _make_wiki(tmp_path: Path) -> Path:
    """Set up a minimal wiki dir with a seeded index."""
    wiki = tmp_path / "wiki"
    for d in ["people", "concepts", "works", "methods", "organizations", "products", "podcasts", "_episodes"]:
        (wiki / d).mkdir(parents=True)
    (wiki / "_index.md").write_text(
        "# Entity Index\n\n| Name | Type | File | Aliases |\n|---|---|---|---|\n"
    )
    return wiki


def test_slugify():
    assert slugify("Andrew Huberman") == "andrew-huberman"
    assert slugify("Dr. Huberman, PhD") == "dr-huberman-phd"
    assert slugify("AG1") == "ag1"


def test_sanitize_slug_strips_dir_prefix():
    assert sanitize_slug("people/elon-musk") == "elon-musk"
    assert sanitize_slug("concepts/mental-health") == "mental-health"
    assert sanitize_slug("Elon Musk") == "elon-musk"
    assert sanitize_slug("") == ""


def test_merge_to_wiki_sanitizes_slug_with_dir_prefix(tmp_path):
    """LLM sometimes emits slug like 'people/elon-musk' — must write
    to wiki/people/elon-musk.md, not wiki/people/people/elon-musk.md."""
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [{"type": "Person", "name": "Elon Musk",
                      "slug": "people/elon-musk", "attributes": {}}],
        "edges": [], "observations": [],
    }
    merge_to_wiki(extraction, "ep1", wiki)
    assert (wiki / "people" / "elon-musk.md").exists()
    assert not (wiki / "people" / "people").exists()


def test_load_page_returns_empty_dict_for_missing_file(tmp_path):
    assert load_page(tmp_path / "nonexistent.md") == {}


def test_load_page_parses_yaml(tmp_path):
    p = tmp_path / "test.md"
    p.write_text("---\nname: Foo\ntype: person\n---\n\n## Body\n")
    fm = load_page(p)
    assert fm["name"] == "Foo"
    assert fm["type"] == "person"


def test_save_page_writes_valid_yaml(tmp_path):
    p = tmp_path / "out.md"
    save_page(p, {"name": "Foo", "type": "person"}, "## Body\nHello")
    text = p.read_text()
    assert text.startswith("---\n")
    assert "name: Foo" in text
    assert "## Body" in text


def test_merge_to_wiki_creates_person_page(tmp_path):
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [{"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman",
                      "attributes": {"expertise": "Neuroscience", "role_context": "Neuroscientist"}}],
        "edges": [],
        "observations": [],
    }
    paths = merge_to_wiki(extraction, "abc123", wiki)
    page_path = wiki / "people" / "andrew-huberman.md"
    assert page_path in paths
    assert page_path.exists()
    fm = load_page(page_path)
    assert fm["name"] == "Andrew Huberman"
    assert fm["type"] == "person"
    assert fm["expertise"] == "Neuroscience"
    assert fm["enriched"] is False


def test_merge_to_wiki_updates_existing_page(tmp_path):
    wiki = _make_wiki(tmp_path)
    # First pass — creates page with minimal attributes
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman",
                      "attributes": {"expertise": "Neuroscience"}}],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    # Second pass — adds credentials
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman",
                      "attributes": {"credentials": "PhD, Stanford"}}],
        "edges": [], "observations": [],
    }, "ep2", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    assert fm["expertise"] == "Neuroscience"   # preserved from pass 1
    assert fm["credentials"] == "PhD, Stanford"  # added in pass 2


def test_merge_to_wiki_adds_edge_to_source_entity(tmp_path):
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [
            {"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman", "attributes": {}},
            {"type": "Concept", "name": "Dopamine", "slug": "dopamine", "attributes": {"domain": "neuroscience"}},
        ],
        "edges": [{
            "type": "Claims",
            "from_name": "Andrew Huberman", "from_type": "Person",
            "to_name": "Dopamine", "to_type": "Concept",
            "attributes": {"insight_type": "claim", "timestamp": "14:23"},
            "episode": "abc123",
        }],
        "observations": [],
    }
    merge_to_wiki(extraction, "abc123", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    assert "claims" in fm["relationships"]
    claim = fm["relationships"]["claims"][0]
    assert claim["entity"] == "[[concepts/dopamine]]"
    assert claim["episode"] == "abc123"


def test_merge_to_wiki_deduplicates_edges(tmp_path):
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [
            {"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman", "attributes": {}},
            {"type": "Concept", "name": "Dopamine", "slug": "dopamine", "attributes": {}},
        ],
        "edges": [{
            "type": "Claims", "from_name": "Andrew Huberman", "from_type": "Person",
            "to_name": "Dopamine", "to_type": "Concept",
            "attributes": {"timestamp": "14:23"}, "episode": "abc123",
        }],
        "observations": [],
    }
    # Run twice with same data
    merge_to_wiki(extraction, "abc123", wiki)
    merge_to_wiki(extraction, "abc123", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    assert len(fm["relationships"]["claims"]) == 1


def test_merge_to_wiki_keeps_edges_at_different_timestamps(tmp_path):
    """Two claims about the same concept at different points in one episode
    must both be preserved — timestamp is part of the dedup key."""
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [
            {"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman", "attributes": {}},
            {"type": "Concept", "name": "Dopamine", "slug": "dopamine", "attributes": {}},
        ],
        "edges": [
            {
                "type": "Claims", "from_name": "Andrew Huberman", "from_type": "Person",
                "to_name": "Dopamine", "to_type": "Concept",
                "attributes": {"timestamp": "14:23", "insight_type": "claim"},
                "episode": "abc123",
            },
            {
                "type": "Claims", "from_name": "Andrew Huberman", "from_type": "Person",
                "to_name": "Dopamine", "to_type": "Concept",
                "attributes": {"timestamp": "31:07", "insight_type": "claim"},
                "episode": "abc123",
            },
        ],
        "observations": [],
    }
    merge_to_wiki(extraction, "abc123", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    claims = fm["relationships"]["claims"]
    assert len(claims) == 2
    timestamps = {c["timestamp"] for c in claims}
    assert timestamps == {"14:23", "31:07"}


def test_merge_to_wiki_adds_observation(tmp_path):
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [{"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman", "attributes": {}}],
        "edges": [],
        "observations": [{"entity_name": "Andrew Huberman", "episode": "abc123",
                          "timestamp": "31:12", "text": "mentions Flow State Labs"}],
    }
    merge_to_wiki(extraction, "abc123", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    assert len(fm["observations"]) == 1
    assert "Flow State Labs" in fm["observations"][0]["text"]


def test_read_index_parses_table(tmp_path):
    wiki = _make_wiki(tmp_path)
    (wiki / "_index.md").write_text(
        "# Entity Index\n\n| Name | Type | File | Aliases |\n|---|---|---|---|\n"
        "| Andrew Huberman | person | people/andrew-huberman | Dr. Huberman, Huberman |\n"
    )
    index = read_index(wiki)
    assert "andrew huberman" in index
    entry = index["andrew huberman"]
    assert entry["file"] == "people/andrew-huberman"
    assert "huberman" in entry["aliases"]


def test_merge_to_wiki_fuzzy_merges_steven_stephen(tmp_path):
    """Spelling variants with >=0.90 ratio collapse to one page."""
    wiki = _make_wiki(tmp_path)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Stephen Bartlett",
                      "slug": "stephen-bartlett", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Steven Bartlett",
                      "slug": "steven-bartlett", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep2", wiki)
    people_pages = list((wiki / "people").glob("*.md"))
    assert len(people_pages) == 1
    fm = load_page(people_pages[0])
    assert "Steven Bartlett" in fm["aliases"]


def test_merge_to_wiki_does_not_merge_unrelated_people(tmp_path):
    """Different people with same first name must stay separate."""
    wiki = _make_wiki(tmp_path)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Andrew Huberman",
                      "slug": "andrew-huberman", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "Andrew Tate",
                      "slug": "andrew-tate", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep2", wiki)
    people_pages = sorted(p.name for p in (wiki / "people").glob("*.md"))
    assert people_pages == ["andrew-huberman.md", "andrew-tate.md"]


def test_merge_to_wiki_does_not_merge_across_types(tmp_path):
    """Same name, different entity type — do not merge."""
    wiki = _make_wiki(tmp_path)
    merge_to_wiki({
        "entities": [
            {"type": "Concept", "name": "Flow", "slug": "flow", "attributes": {}},
            {"type": "Product", "name": "Flow", "slug": "flow", "attributes": {}},
        ],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    assert (wiki / "concepts" / "flow.md").exists()
    assert (wiki / "products" / "flow.md").exists()


def test_merge_to_wiki_drops_single_token_person_without_attrs(tmp_path):
    """Unresolved speaker labels ('Dom') must not create pages."""
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [
            {"type": "Person", "name": "Dom", "slug": "dom", "attributes": {}},
            {"type": "Person", "name": "Andrew Huberman",
             "slug": "andrew-huberman", "attributes": {}},
        ],
        "edges": [], "observations": [],
    }
    merge_to_wiki(extraction, "ep1", wiki)
    assert not (wiki / "people" / "dom.md").exists()
    assert (wiki / "people" / "andrew-huberman.md").exists()


def test_merge_to_wiki_keeps_single_token_person_with_role(tmp_path):
    """Single-token name with a role_context attribute is legit — keep it."""
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [{"type": "Person", "name": "Madonna", "slug": "madonna",
                      "attributes": {"role_context": "Singer"}}],
        "edges": [], "observations": [],
    }
    merge_to_wiki(extraction, "ep1", wiki)
    assert (wiki / "people" / "madonna.md").exists()


def test_merge_to_wiki_drops_edges_to_junk_person(tmp_path):
    """Edges targeting a dropped junk Person must also be dropped."""
    wiki = _make_wiki(tmp_path)
    extraction = {
        "entities": [
            {"type": "Person", "name": "Dom", "slug": "dom", "attributes": {}},
            {"type": "Person", "name": "Andrew Huberman",
             "slug": "andrew-huberman", "attributes": {}},
        ],
        "edges": [{
            "type": "WorksWith",
            "from_name": "Andrew Huberman", "from_type": "Person",
            "to_name": "Dom", "to_type": "Person",
            "attributes": {}, "episode": "ep1",
        }],
        "observations": [],
    }
    merge_to_wiki(extraction, "ep1", wiki)
    fm = load_page(wiki / "people" / "andrew-huberman.md")
    assert "works_with" not in fm["relationships"]


def test_merge_to_wiki_updates_index(tmp_path):
    wiki = _make_wiki(tmp_path)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "New Person", "slug": "new-person", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    index = read_index(wiki)
    assert "new person" in index
