from unittest.mock import MagicMock, patch

from src.retrieval.query_decomposer import decompose_query

QUERY = "How do transformer models compare to RNNs for sequence modeling?"
API_KEY = "test-key"


def _mock_response(text: str) -> MagicMock:
    content = MagicMock()
    content.text = text
    response = MagicMock()
    response.content = [content]
    return response


def test_valid_json_array_is_parsed():
    sub_questions = [
        "What are the architectural differences between transformers and RNNs?",
        "How do transformers handle long-range dependencies compared to RNNs?",
    ]
    json_response = str(sub_questions).replace("'", '"')

    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.return_value = _mock_response(json_response)

        result = decompose_query(QUERY, API_KEY)

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(q, str) for q in result)


def test_malformed_json_falls_back_to_original_query():
    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.return_value = _mock_response("this is not json {{{")

        result = decompose_query(QUERY, API_KEY)

    assert result == [QUERY]


def test_empty_response_falls_back_to_original_query():
    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.return_value = _mock_response("")

        result = decompose_query(QUERY, API_KEY)

    assert result == [QUERY]


def test_api_exception_falls_back_to_original_query():
    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.side_effect = Exception("network error")

        result = decompose_query(QUERY, API_KEY)

    assert result == [QUERY]


def test_max_sub_questions_is_respected():
    many = ["q1", "q2", "q3", "q4", "q5", "q6"]
    json_response = str(many).replace("'", '"')

    with patch("anthropic.Anthropic") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        client.messages.create.return_value = _mock_response(json_response)

        result = decompose_query(QUERY, API_KEY, max_sub_questions=3)

    assert len(result) <= 3
