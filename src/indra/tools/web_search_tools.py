"""Web search tool: queries a local SearXNG instance for current information.

Token discipline: snippets are hard-truncated and results capped, per
the design's "never let search cost more than a memory retrieval"
rule. Results are cached (search_cache table) by a hash of the
normalized query, so repeated/near-duplicate queries within a task or
across tasks cost zero network round-trips within the TTL.

SearXNG must have JSON output enabled (``search.formats: [html, json]``
in its ``settings.yml``) -- it's disabled by default in many installs.
If it's not enabled, this tool fails with a clear, actionable error
instead of a confusing parse error.
"""

from __future__ import annotations

import hashlib
import time

import httpx

from indra.config.schema import WebSearchConfig
from indra.storage.repositories import SearchCacheRepository
from indra.tools.base import ToolResult, ToolSchema

WEB_SEARCH_SCHEMA = ToolSchema(
    name="web_search",
    description=(
        "Search the web for current information not in your training data "
        "(news, current events, prices, recent releases). Returns ranked "
        "title/url/snippet results, not full pages."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
)

_SNIPPET_CHARS = 280
_TITLE_CHARS = 120


class WebSearchTool:
    schema = WEB_SEARCH_SCHEMA

    def __init__(
        self,
        config: WebSearchConfig,
        cache: SearchCacheRepository,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.cache = cache
        self._client = client or httpx.Client()

    def run(self, params: dict) -> ToolResult:
        if not self.config.base_url:
            return ToolResult(
                success=False,
                error="web_search.base_url is not configured",
                retryable=False,
            )

        query = params["query"]
        max_results = min(int(params.get("max_results", self.config.max_results)), self.config.max_results)
        cache_key = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()

        cached = self.cache.get(cache_key)
        if cached is not None:
            return ToolResult(success=True, output={"results": cached[:max_results]})

        start = time.monotonic()
        try:
            resp = self._client.get(
                f"{self.config.base_url.rstrip('/')}/search",
                params={"q": query, "format": "json"},
                timeout=self.config.fetch_timeout_seconds,
            )
            resp.raise_for_status()
        except httpx.TimeoutException:
            return ToolResult(success=False, error="web search timed out", retryable=True)
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                success=False,
                error=(
                    f"web search returned HTTP {exc.response.status_code}. If this is "
                    "SearXNG, check that 'json' is enabled under search.formats in "
                    "settings.yml -- it's off by default on many installs."
                ),
                retryable=False,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"web search request failed: {exc}", retryable=True)

        try:
            data = resp.json()
        except ValueError:
            return ToolResult(
                success=False,
                error=(
                    "web search did not return JSON. If this is SearXNG, enable "
                    "'json' under search.formats in settings.yml and restart it."
                ),
                retryable=False,
            )

        results = [
            {
                "title": (item.get("title") or "")[:_TITLE_CHARS],
                "url": item.get("url", ""),
                "snippet": (item.get("content") or "")[:_SNIPPET_CHARS],
            }
            for item in data.get("results", [])[: self.config.max_results]
        ]
        self.cache.set(
            cache_key, query, results,
            provider=self.config.provider, ttl_seconds=self.config.cache_ttl_seconds,
        )
        return ToolResult(
            success=True,
            output={"results": results[:max_results]},
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def register_web_search_tool(
    registry, config: WebSearchConfig, cache: SearchCacheRepository, client: httpx.Client | None = None
) -> None:
    registry.register(WebSearchTool(config, cache, client))
