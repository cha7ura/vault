from unittest.mock import patch, MagicMock
from scripts.agents.llm import llm_call, llm_json_call


def test_llm_call_returns_response_text():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "  SUBSTANTIVE  "}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp) as mock_post:
        result = llm_call("Is this filler?")

    assert result == "SUBSTANTIVE"
    call_args = mock_post.call_args
    assert "api/generate" in call_args[0][0]


def test_llm_json_call_strips_markdown_fencing():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": '```json\n{"key": "value"}\n```'}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result == {"key": "value"}


def test_llm_json_call_returns_none_on_bad_json():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "not json at all"}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result is None
