import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import pytest
from scripts.agents.wiki_extract import extract_chunk_json, write_episode_summary


# Mock fixture in the strict-schema KV-pair shape returned by Groq.
MOCK_EXTRACTION = {
    "entities": [
        {"type": "Person", "name": "Andrew Huberman", "slug": "andrew-huberman",
         "attributes": [{"key": "expertise", "value": "Neuroscience"}]},
        {"type": "Concept", "name": "Dopamine", "slug": "dopamine",
         "attributes": [{"key": "domain", "value": "neuroscience"}]},
    ],
    "edges": [{
        "type": "Claims", "from_name": "Andrew Huberman", "from_type": "Person",
        "to_name": "Dopamine", "to_type": "Concept",
        "attributes": [
            {"key": "insight_type", "value": "claim"},
            {"key": "timestamp", "value": "14:23"},
        ],
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


def test_extract_chunk_json_converts_kv_attributes_to_dict():
    """The LLM returns attributes as KV-pair arrays (strict-schema constraint);
    wiki_writer expects dicts. Conversion must happen in extract_chunk_json."""
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        mock_post.return_value = _mock_groq_response(MOCK_EXTRACTION)
        result = extract_chunk_json("text", "idx")
    assert result["entities"][0]["attributes"] == {"expertise": "Neuroscience"}
    assert result["entities"][1]["attributes"] == {"domain": "neuroscience"}
    assert result["edges"][0]["attributes"] == {
        "insight_type": "claim", "timestamp": "14:23"
    }


def test_extract_chunk_json_sends_strict_json_schema():
    """Verify the request uses strict:true structured outputs, not loose json_object."""
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        mock_post.return_value = _mock_groq_response(MOCK_EXTRACTION)
        extract_chunk_json("text", "idx")
    payload = mock_post.call_args.kwargs["json"]
    rf = payload["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "wiki_extraction"
    schema = rf["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"entities", "edges", "observations"}


def test_extract_chunk_json_returns_empty_structure_on_bad_json():
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "not json {"}}]}
        mock_post.return_value = resp
        result = extract_chunk_json("text", "index")
    assert result == {"entities": [], "edges": [], "observations": []}


def test_extract_chunk_json_recovers_from_failed_generation():
    """When Groq strict returns 400 with failed_generation, we salvage it
    and backfill any missing required arrays."""
    partial = {
        "entities": [
            {"type": "Person", "name": "X", "slug": "x",
             "attributes": [{"key": "k", "value": "v"}]},
        ],
        "edges": [],
        # note: observations is missing — this is what triggers the 400
    }
    with patch("scripts.agents.wiki_extract.requests.post") as mock_post:
        resp = MagicMock()
        resp.status_code = 400
        resp.json.return_value = {
            "error": {
                "code": "json_validate_failed",
                "failed_generation": json.dumps(partial),
            }
        }
        resp.text = "400 body"
        mock_post.return_value = resp
        result = extract_chunk_json("text", "idx")
    assert result["entities"][0]["name"] == "X"
    assert result["entities"][0]["attributes"] == {"k": "v"}
    assert result["edges"] == []
    assert result["observations"] == []


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
