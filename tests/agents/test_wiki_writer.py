import tempfile
from pathlib import Path
import yaml
import pytest
from scripts.agents.wiki_writer import (
    slugify,
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


def test_merge_to_wiki_updates_index(tmp_path):
    wiki = _make_wiki(tmp_path)
    merge_to_wiki({
        "entities": [{"type": "Person", "name": "New Person", "slug": "new-person", "attributes": {}}],
        "edges": [], "observations": [],
    }, "ep1", wiki)
    index = read_index(wiki)
    assert "new person" in index
