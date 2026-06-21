"""웹 검색 서비스 — DuckDuckGo (API 키 불필요)."""
import asyncio
import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def _search_sync(query: str, max_results: int = 6) -> list[dict]:
    results = DDGS().text(query, max_results=max_results, region="kr-kr")
    return list(results) if results else []


async def web_search(query: str, max_results: int = 6) -> list[dict]:
    """Return list of {title, href, body} dicts. Returns [] on error."""
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception as e:
        logger.warning("web_search failed for %r: %s", query, e)
        return []


def format_search_context(results: list[dict]) -> str:
    """Format search results as an LLM-readable context block."""
    if not results:
        return ""
    lines = ["[실시간 웹 검색 결과 — 아래 정보를 참고해 사실 기반 스크립트를 작성하세요]"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        body = r.get("body", "").strip()[:350]
        if title or body:
            lines.append(f"\n[{i}] {title}")
            if body:
                lines.append(f"    {body}")
    return "\n".join(lines)
