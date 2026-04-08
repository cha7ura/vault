import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import pytest
from scripts.agents.wiki_extract import extract_chunk_json, write_episode_summary


MOCK_EXTRACTION = {
    "entities": [
        {"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman",
         "attributes": {"expertise": "Neuroscience"}},
        {"type": "Concept", "name": "Dopamine", "slug": "dopamine",
         "attributes": {"domain": "neuroscience"}},
    ],
    "edges": [{
        "type": "Claims", "from_name": "Andrew Huberman", "from_type": "Person",
        "to_name": "Dopamine", "to_type": "Concept",
        "attributes": {"insight_type": "claim", "timestamp": "14:23"},
        "episode": "abc123",
    }],
    "observations": [],
}


def _mock_groq_response(content: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(content)}}]
    }
    return resp


def test_extract_chunk_json_returns_entities_and_edges():
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        mock_post.return_value = _mock_groq_response(MOCK_EXTRACTION)
        result = extract_chunk_json("some transcript text", "# Index\n| Name | ...\n")
    assert "entities" in result
    assert "edges" in result
    assert "observations" in result
    assert result["entities"][0]["name"] == "Andrew Huberman"


def test_extract_chunk_json_returns_empty_structure_on_bad_json():
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "not json {"}}]}
        mock_post.return_value = resp
        result = extract_chunk_json("text", "index")
    assert result == {"entities": [], "edges": [], "observations": []}


def test_extract_chunk_json_returns_empty_on_api_error():
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "rate limit"
        mock_post.return_value = resp
        result = extract_chunk_json("text", "index")
    assert result == {"entities": [], "edges": [], "observations": []}


def test_write_episode_summary_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        wiki_dir = Path(tmpdir)
        (wiki_dir / "_episodes").mkdir()
        episode = {
            "youtube_id": "abc123",
            "title": "Test Episode",
            "published_at": "2023-01-15",
            "guest_name": "Andrew Huberman",
        }
        touched_texts = ["## Andrew Huberman\nexpertise: Neuroscience"]
        mock_body = "## Summary\nTest summary content"
        with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"choices": [{"message": {"content": mock_body}}]}
            mock_post.return_value = resp
            write_episode_summary(episode, touched_texts, wiki_dir)
        ep_path = wiki_dir / "_episodes" / "abc123.md"
        assert ep_path.exists()
        assert "abc123" in ep_path.read_text()
