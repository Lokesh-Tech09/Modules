"""
Genuine Web/Social Discovery Layer — shared/search_adapter.py

Performs a REAL web search to discover publicly available social/web posts
matching a candidate name or query. This is NOT a hardcoded result.

Architecture:
- Primary:  duckduckgo-search (pip install duckduckgo-search) — no API key needed
- Fallback: DuckDuckGo HTML scraping via requests — still no API key
- Future:   Replace with SerpAPI/Google Custom Search by subclassing SearchAdapter

The discovery layer is deliberately isolated here so Module 2 can receive
genuinely discovered URLs rather than pre-selected hardcoded links.

IMPORTANT:
- Never hardcode a specific post URL as a search "result".
- Always filter results for likely social/web profile posts.
- Return an empty list + clear warning if nothing is found rather than fabricating a result.
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import quote_plus, urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base — swap implementations without touching the pipeline
# ---------------------------------------------------------------------------

class SearchAdapter(ABC):
    """Base interface for genuine web/social discovery."""

    @abstractmethod
    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[str]:
        """
        Perform a genuine web search and return a list of discovered URLs.

        Args:
            query: Search query string (candidate name, keywords, etc.)
            max_results: Maximum number of result URLs to return.

        Returns:
            List of discovered URLs (may be empty if nothing found).
        """
        ...


# ---------------------------------------------------------------------------
# DuckDuckGo implementation (primary, no API key)
# ---------------------------------------------------------------------------

class DuckDuckGoSearchAdapter(SearchAdapter):
    """
    Genuine search using the `duckduckgo-search` library.
    No API key required. Results are real-time web discoveries.
    """

    # Social/profile domains we prefer for face-trace matching
    PREFERRED_DOMAINS = [
        "twitter.com", "x.com",
        "instagram.com",
        "linkedin.com",
        "facebook.com",
        "reddit.com",
        "youtube.com",
        "tiktok.com",
        "github.com",
        "medium.com",
    ]

    def __init__(self, delay_seconds: float = 1.5):
        """
        Args:
            delay_seconds: Polite delay between requests to avoid rate-limiting.
        """
        self.delay_seconds = delay_seconds
        self._ddgs = None

    def _get_ddgs(self):
        """Lazy-initialize DDGS client."""
        if self._ddgs is None:
            try:
                # Try the new package name first (ddgs), fall back to duckduckgo_search
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                self._ddgs = DDGS()
            except ImportError:
                raise ImportError(
                    "Install search package: pip install ddgs  (or: pip install duckduckgo-search)"
                )
        return self._ddgs

    def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[str]:
        """
        Perform a real DuckDuckGo search and return discovered URLs.

        Preference is given to social/profile domains.
        Results are not filtered to a specific hardcoded site.
        """
        logger.info("[Search] DuckDuckGo search: %r (max=%d)", query, max_results)
        time.sleep(self.delay_seconds)  # polite delay

        try:
            ddgs = self._get_ddgs()
            raw_results = list(ddgs.text(query, max_results=max_results * 2))
        except Exception as exc:
            logger.warning("[Search] DuckDuckGo search failed: %s", exc)
            return []

        if not raw_results:
            logger.warning("[Search] DuckDuckGo returned 0 results for: %r", query)
            return []

        urls = []
        for item in raw_results:
            url = item.get("href") or item.get("url", "")
            if url and url.startswith("http"):
                urls.append(url)

        # Sort: preferred social domains first
        def domain_priority(url: str) -> int:
            try:
                host = urlparse(url).netloc.lower().replace("www.", "")
                for i, domain in enumerate(self.PREFERRED_DOMAINS):
                    if domain in host:
                        return i
                return len(self.PREFERRED_DOMAINS)
            except Exception:
                return 999

        urls.sort(key=domain_priority)
        top = urls[:max_results]
        logger.info("[Search] Found %d URLs: %s", len(top), top)
        return top


# ---------------------------------------------------------------------------
# HTML scrape fallback (no external library needed)
# ---------------------------------------------------------------------------

class DuckDuckGoHTMLAdapter(SearchAdapter):
    """
    Fallback: scrape DuckDuckGo HTML search results with requests + BeautifulSoup.
    Used if `duckduckgo-search` package is unavailable.
    """

    DDG_URL = "https://html.duckduckgo.com/html/"

    def search(self, query: str, max_results: int = 5) -> List[str]:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("[Search] requests + beautifulsoup4 required for fallback scraper.")
            return []

        logger.info("[Search] DuckDuckGo HTML scrape: %r", query)
        time.sleep(1.5)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = requests.post(
                self.DDG_URL,
                data={"q": query, "b": "", "kl": "us-en"},
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("[Search] HTML scrape request failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if href.startswith("http"):
                links.append(href)
            if len(links) >= max_results:
                break

        logger.info("[Search] HTML scrape found %d URLs", len(links))
        return links[:max_results]


# ---------------------------------------------------------------------------
# SerpAPI stub — drop-in future replacement
# ---------------------------------------------------------------------------

class SerpAPISearchAdapter(SearchAdapter):
    """
    Future replacement: SerpAPI / Google Custom Search.
    Requires SERPAPI_KEY environment variable.
    """

    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "")
        if not self.api_key:
            raise EnvironmentError(
                "SERPAPI_KEY environment variable is not set. "
                "Set it in .env to use SerpAPI search."
            )

    def search(self, query: str, max_results: int = 5) -> List[str]:
        try:
            from serpapi import GoogleSearch
        except ImportError:
            raise ImportError("pip install google-search-results to use SerpAPISearchAdapter.")

        params = {
            "q": query,
            "api_key": self.api_key,
            "num": max_results,
            "engine": "google",
        }
        client = GoogleSearch(params)
        results = client.get_dict()
        organic = results.get("organic_results", [])
        return [r["link"] for r in organic if "link" in r][:max_results]


# ---------------------------------------------------------------------------
# Factory — select best available adapter
# ---------------------------------------------------------------------------

def get_search_adapter() -> SearchAdapter:
    """
    Return the best available search adapter based on installed packages
    and environment configuration.

    Priority:
    1. SerpAPI (if SERPAPI_KEY is set and google-search-results installed)
    2. duckduckgo-search library (primary, free, no API key)
    3. DuckDuckGo HTML scraper (fallback, no libraries needed)
    """
    # Check for SerpAPI override
    if os.getenv("SERPAPI_KEY"):
        try:
            adapter = SerpAPISearchAdapter()
            logger.info("[Search] Using SerpAPI adapter.")
            return adapter
        except Exception as e:
            logger.warning("[Search] SerpAPI unavailable: %s. Falling back.", e)

    # Try duckduckgo-search library (preferred free option)
    try:
        try:
            from ddgs import DDGS  # noqa: F401 — new package name
        except ImportError:
            from duckduckgo_search import DDGS  # noqa: F401 — legacy name
        logger.info("[Search] Using DuckDuckGo DDGS adapter.")
        return DuckDuckGoSearchAdapter()
    except ImportError:
        pass

    # Last resort: HTML scraper
    logger.warning(
        "[Search] duckduckgo-search not installed. "
        "Using DuckDuckGo HTML scraper fallback. "
        "Install with: pip install duckduckgo-search"
    )
    return DuckDuckGoHTMLAdapter()


# ---------------------------------------------------------------------------
# High-level convenience function used by the pipeline
# ---------------------------------------------------------------------------

def discover_social_posts(
    candidate_name: Optional[str],
    extra_keywords: Optional[str] = None,
    max_results: int = 5,
    adapter: Optional[SearchAdapter] = None,
) -> List[str]:
    """
    Perform a genuine web/social search for a named candidate and return
    discovered post/profile URLs.

    This function is the main entry point used by the E2E pipeline.
    It is intentionally non-deterministic — results depend on what the
    search engine returns at query time.

    Args:
        candidate_name: Name of the identified person (from Module 1).
                        If None or empty, a broad query is used.
        extra_keywords: Additional search terms (e.g. "photo", "post", "profile").
        max_results: Maximum number of URLs to return.
        adapter: Optional pre-configured SearchAdapter instance.

    Returns:
        List of genuinely discovered URLs (may be empty).

    Raises:
        Nothing — all errors are logged and an empty list is returned.
    """
    if not candidate_name or candidate_name.strip() == "":
        logger.warning(
            "[Discovery] No candidate name provided. "
            "Cannot perform meaningful web search. "
            "Returning empty URL list."
        )
        return []

    # Build meaningful search query
    query_parts = [candidate_name.strip()]
    if extra_keywords:
        query_parts.append(extra_keywords.strip())
    else:
        # Default: look for social profiles / posts
        query_parts.append("social media profile post photo")

    query = " ".join(query_parts)
    logger.info("[Discovery] Search query: %r", query)

    if adapter is None:
        try:
            adapter = get_search_adapter()
        except Exception as exc:
            logger.error("[Discovery] Failed to get search adapter: %s", exc)
            return []

    try:
        urls = adapter.search(query, max_results=max_results)
        if not urls:
            logger.warning(
                "[Discovery] Search returned 0 results for candidate %r. "
                "This is not fabricated — genuine search found nothing.",
                candidate_name,
            )
        return urls
    except Exception as exc:
        logger.error("[Discovery] Search raised unexpected error: %s", exc)
        return []
