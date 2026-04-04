from unittest.mock import patch, MagicMock
from scripts.agents.llm import llm_call, llm_json_call


def test_llm_call_returns_response_text():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "  SUBSTANTIVE  "}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp) as mock_post:
        result = llm_call("Is this filler?")

    assert result == "SUBSTANTIVE"
    call_args = mock_post.call_args
    assert "chat/completions" in call_args[0][0]


def test_llm_json_call_strips_markdown_fencing():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": '```json\n{"key": "value"}\n```'}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result == {"key": "value"}


def test_llm_json_call_returns_none_on_bad_json():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "not json at all"}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp):
        result = llm_json_call("Extract JSON")

    assert result is None


def test_llm_call_adds_no_think_prefix():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp) as mock_post:
        llm_call("test", think=False)

    body = mock_post.call_args[1]["json"]
    assert body["messages"][0]["content"].startswith("/no_think")


def test_llm_call_skips_no_think_when_think_true():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
    mock_resp.raise_for_status = MagicMock()

    with patch("scripts.agents.llm.requests.post", return_value=mock_resp) as mock_post:
        llm_call("test", think=True)

    body = mock_post.call_args[1]["json"]
    assert not body["messages"][0]["content"].startswith("/no_think")
