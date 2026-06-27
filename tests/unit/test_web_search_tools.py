from __future__ import annotations

import httpx
import pytest

from indra.config.schema import WebSearchConfig
from indra.storage.db import Database
from indra.storage.repositories import SearchCacheRepository
from indra.tools.web_search_tools import WebSearchTool


def _client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def cache(tmp_path) -> SearchCacheRepository:
    db = Database(str(tmp_path / "indra.db"))
    db.migrate()
    return SearchCacheRepository(db)


def test_successful_search_returns_truncated_results(cache: SearchCacheRepository) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "A" * 200, "url": "http://example.com/a", "content": "B" * 500},
                ]
            },
        )

    config = WebSearchConfig(base_url="http://localhost:8088", max_results=5)
    tool = WebSearchTool(config, cache, client=_client_with(handler))
    result = tool.run({"query": "test query"})

    assert result.success
    hit = result.output["results"][0]
    assert len(hit["title"]) == 120
    assert len(hit["snippet"]) == 280
    assert hit["url"] == "http://example.com/a"


def test_missing_base_url_fails_without_a_network_call(cache: SearchCacheRepository) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should never be called")

    config = WebSearchConfig(base_url="")
    tool = WebSearchTool(config, cache, client=_client_with(handler))
    result = tool.run({"query": "test"})
    assert not result.success
    assert result.retryable is False


def test_non_json_response_gives_actionable_searxng_hint(cache: SearchCacheRepository) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    config = WebSearchConfig(base_url="http://localhost:8088")
    tool = WebSearchTool(config, cache, client=_client_with(handler))
    result = tool.run({"query": "test"})
    assert not result.success
    assert "settings.yml" in result.error


def test_results_are_cached_and_second_call_skips_the_network(cache: SearchCacheRepository) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"results": [{"title": "T", "url": "u", "content": "c"}]})

    config = WebSearchConfig(base_url="http://localhost:8088", cache_ttl_seconds=3600)
    tool = WebSearchTool(config, cache, client=_client_with(handler))

    tool.run({"query": "same query"})
    tool.run({"query": "  Same Query  "})  # normalized to the same cache key

    assert calls["count"] == 1


def test_http_error_status_gives_searxng_json_hint(cache: SearchCacheRepository) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    config = WebSearchConfig(base_url="http://localhost:8088")
    tool = WebSearchTool(config, cache, client=_client_with(handler))
    result = tool.run({"query": "test"})
    assert not result.success
    assert "403" in result.error
    assert "settings.yml" in result.error
