from unittest.mock import patch, MagicMock
from scripts.agents.search import searxng_search


def test_searxng_search_returns_results():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "Dr. Huberman", "url": "https://example.com", "content": "Neuroscientist"},
            {"title": "Huberman Lab", "url": "https://example2.com", "content": "Podcast"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.search.requests.get", return_value=mock_resp):
        results = searxng_search("Andrew Huberman", engines="google,wikipedia")

    assert len(results) == 2
    assert results[0]["title"] == "Dr. Huberman"


def test_searxng_search_returns_empty_on_failure():
    with patch("scripts.agents.search.requests.get", side_effect=Exception("timeout")):
        results = searxng_search("anything")

    assert results == []
