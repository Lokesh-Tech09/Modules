"""
Async candidate fetcher for Module 2: Claimed-Profile Verification (v2).
Provides:
- Asynchronous fetching with bounded concurrency (asyncio.Semaphore).
- Exponential backoff retry for transient network/5xx errors.
- Per-domain circuit breaker to prevent hammering unresponsive hosts.
- Respects robots.txt policies per domain.
- Enforces SSRF security checks, domain allow/denylists, and streaming size limits.
- Marks CAPTCHA / paywall / auth-restricted pages as FetchStatus.BLOCKED without bypass.
"""

import asyncio
import io
import logging
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import urllib.robotparser

import httpx

from .config import VerificationConfig, default_config
from .models import CandidateFetchResult, ExtractedPostMetadata, FetchStatus
from .post_extractor import PostExtractor
from .security import DomainPolicy, SSRFGuard, URLSanitizer
from .utils import save_temp_image, validate_image_data

logger = logging.getLogger(__name__)


class DomainCircuitBreaker:
    """
    Per-domain circuit breaker tracking consecutive failures.
    Short-circuits requests to domains experiencing cascading outages.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_counts: Dict[str, int] = {}
        self.tripped_at: Dict[str, float] = {}

    def is_available(self, domain: str) -> bool:
        """Check if domain circuit is closed (available) or open (tripped)."""
        domain = domain.lower()
        if domain in self.tripped_at:
            if time.time() - self.tripped_at[domain] > self.reset_timeout:
                # Reset circuit after timeout (half-open test)
                del self.tripped_at[domain]
                self.failure_counts[domain] = 0
                return True
            return False
        return True

    def record_success(self, domain: str) -> None:
        domain = domain.lower()
        self.failure_counts[domain] = 0
        if domain in self.tripped_at:
            del self.tripped_at[domain]

    def record_failure(self, domain: str) -> None:
        domain = domain.lower()
        count = self.failure_counts.get(domain, 0) + 1
        self.failure_counts[domain] = count
        if count >= self.failure_threshold:
            self.tripped_at[domain] = time.time()
            logger.warning(f"Circuit breaker TRIPPED for domain '{domain}' after {count} consecutive failures.")


class RobotsTxtCache:
    """In-memory cache for domain robots.txt rules."""

    def __init__(self, user_agent: str, timeout: float = 5.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self.parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}

    async def can_fetch(self, url: str, client: httpx.AsyncClient) -> bool:
        """Check if user-agent is permitted to fetch URL according to domain's robots.txt."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return True

        if domain not in self.parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                resp = await client.get(robots_url, timeout=self.timeout)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # If 404 or absent, crawling is permitted
                    rp.allow_all = True
            except Exception:
                # Network failure fetching robots.txt defaults to permissible
                rp.allow_all = True
            self.parsers[domain] = rp

        return self.parsers[domain].can_fetch(self.user_agent, url)


class CandidateFetcher:
    """
    Production-ready asynchronous candidate fetcher (v2).
    """

    TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(self, config: Optional[VerificationConfig] = None):
        self.config = config or default_config
        self.domain_policy = DomainPolicy(
            allowlist=self.config.DOMAIN_ALLOWLIST,
            denylist=self.config.DOMAIN_DENYLIST,
        )
        self.circuit_breaker = DomainCircuitBreaker(
            failure_threshold=self.config.CIRCUIT_BREAKER_THRESHOLD,
            reset_timeout=float(self.config.CIRCUIT_BREAKER_RESET_TIMEOUT),
        )
        self.robots_cache = RobotsTxtCache(
            user_agent=self.config.USER_AGENT,
            timeout=min(5.0, float(self.config.REQUEST_TIMEOUT_SECONDS)),
        )
        self.semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_FETCHES)

    async def fetch_candidate(
        self,
        url: str,
        post_extractor: Optional[PostExtractor] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> CandidateFetchResult:
        """
        Fetch a single claimed URL asynchronously with retry and circuit breaker logic.
        """
        start_time = time.time()
        extractor = post_extractor or PostExtractor()

        # Step 1: Sanitize and validate URL format
        is_valid, clean_url, sanitization_err = URLSanitizer.sanitize(
            url, enforce_https=self.config.ENFORCE_HTTPS_ONLY
        )
        if not is_valid or not clean_url:
            return CandidateFetchResult(
                url=url,
                fetch_status=FetchStatus.FAILED,
                error_message=sanitization_err,
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )

        parsed = urlparse(clean_url)
        domain = parsed.netloc.lower()

        # Step 2: Domain policy check (allowlist/denylist)
        allowed, domain_err = self.domain_policy.is_domain_allowed(parsed.hostname or "")
        if not allowed:
            return CandidateFetchResult(
                url=clean_url,
                fetch_status=FetchStatus.BLOCKED,
                error_message=domain_err,
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )

        # Step 3: SSRF check
        if self.config.ENABLE_SSRF_PROTECTION:
            safe, ssrf_err = SSRFGuard.validate_host(parsed.hostname or "")
            if not safe:
                return CandidateFetchResult(
                    url=clean_url,
                    fetch_status=FetchStatus.FAILED,
                    error_message=ssrf_err,
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                )

        # Step 4: Circuit breaker check
        if not self.circuit_breaker.is_available(domain):
            return CandidateFetchResult(
                url=clean_url,
                fetch_status=FetchStatus.FAILED,
                error_message=f"Circuit breaker is OPEN for domain '{domain}' due to repeated failures.",
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )

        # Step 5: Execute fetch bounded by semaphore
        async with self.semaphore:
            created_local_client = False
            if client is None:
                client = httpx.AsyncClient(
                    headers={"User-Agent": self.config.USER_AGENT},
                    timeout=float(self.config.REQUEST_TIMEOUT_SECONDS),
                    follow_redirects=True,
                    max_redirects=self.config.MAX_REDIRECTS,
                )
                created_local_client = True

            try:
                # Step 5a: Robots.txt check if enabled
                if self.config.RESPECT_ROBOTS_TXT:
                    can_crawl = await self.robots_cache.can_fetch(clean_url, client)
                    if not can_crawl:
                        return CandidateFetchResult(
                            url=clean_url,
                            fetch_status=FetchStatus.BLOCKED,
                            error_message="Access disallowed by domain's robots.txt policy.",
                            duration_ms=round((time.time() - start_time) * 1000, 2),
                        )

                # Step 5b: Fetch with retry loop for transient failures
                result = await self._fetch_with_retries(clean_url, extractor, client)
                result.duration_ms = round((time.time() - start_time) * 1000, 2)

                if result.fetch_status == FetchStatus.SUCCESS:
                    self.circuit_breaker.record_success(domain)
                elif result.fetch_status == FetchStatus.FAILED:
                    self.circuit_breaker.record_failure(domain)

                return result
            finally:
                if created_local_client:
                    await client.aclose()

    async def _fetch_with_retries(
        self,
        url: str,
        extractor: PostExtractor,
        client: httpx.AsyncClient,
    ) -> CandidateFetchResult:
        """Perform request with exponential backoff for transient errors."""
        retries = 0
        max_retries = max(1, self.config.MAX_RETRIES)

        while retries < max_retries:
            try:
                async with client.stream("GET", url) as resp:
                    status = resp.status_code

                    # Access restriction / CAPTCHA / paywall -> mark BLOCKED
                    if status in (401, 403):
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.BLOCKED,
                            error_message=f"Access restricted (HTTP {status}). Login/auth bypass prohibited.",
                            retries_used=retries,
                        )

                    # Transient server error -> retry
                    if status in self.TRANSIENT_STATUS_CODES and retries < max_retries - 1:
                        retries += 1
                        await asyncio.sleep(self.config.RETRY_BACKOFF_FACTOR * (2 ** (retries - 1)))
                        continue

                    if status != 200:
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.FAILED,
                            error_message=f"HTTP {status} {resp.reason_phrase}",
                            retries_used=retries,
                        )

                    # Redirect to login page check
                    final_path = resp.url.path.lower()
                    if any(kw in final_path for kw in ("/login", "/signin", "/accounts/login")):
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.BLOCKED,
                            error_message="Redirected to authentication page. Private content cannot be verified.",
                            retries_used=retries,
                        )

                    content_type = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()

                    # Case A: Direct Image
                    if content_type.startswith("image/"):
                        image_bytes, read_err = await self._read_stream(resp)
                        if read_err:
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.FAILED,
                                error_message=read_err,
                                retries_used=retries,
                            )

                        valid, mime, img_err = validate_image_data(
                            image_bytes, self.config.ALLOWED_IMAGE_MIME_TYPES
                        )
                        if not valid:
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.FAILED,
                                error_message=f"Invalid image: {img_err}",
                                retries_used=retries,
                            )

                        local_path = save_temp_image(image_bytes, self.config.TEMP_DIR)
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.SUCCESS,
                            content_type=mime,
                            image_bytes=image_bytes,
                            local_image_path=local_path,
                            retries_used=retries,
                        )

                    # Case B: HTML Post
                    elif "text/html" in content_type or "application/xhtml" in content_type:
                        html_bytes, read_err = await self._read_stream(resp, max_bytes=5 * 1024 * 1024)
                        if read_err:
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.FAILED,
                                error_message=read_err,
                                retries_used=retries,
                            )

                        html_text = html_bytes.decode(resp.encoding or "utf-8", errors="replace")

                        # Check for CAPTCHA
                        if self._is_captcha_page(html_text):
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.BLOCKED,
                                html_content=html_text,
                                error_message="Page presented a CAPTCHA challenge. Bypassing CAPTCHAs is prohibited.",
                                retries_used=retries,
                            )

                        extracted = extractor.extract(html_text, base_url=str(resp.url))
                        if not extracted.image_url:
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.FAILED,
                                html_content=html_text,
                                error_message="No primary image found in post's public metadata.",
                                retries_used=retries,
                            )

                        # Fetch the extracted image
                        img_bytes, mime, fetch_err = await self._download_image_bytes(
                            extracted.image_url, client
                        )
                        if fetch_err or not img_bytes:
                            return CandidateFetchResult(
                                url=url,
                                fetch_status=FetchStatus.FAILED,
                                html_content=html_text,
                                error_message=f"Failed to fetch post image ({extracted.image_url}): {fetch_err}",
                                retries_used=retries,
                            )

                        local_path = save_temp_image(img_bytes, self.config.TEMP_DIR)
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.SUCCESS,
                            content_type=mime,
                            image_bytes=img_bytes,
                            local_image_path=local_path,
                            html_content=html_text,
                            extracted_metadata=extracted,
                            retries_used=retries,
                        )

                    else:
                        return CandidateFetchResult(
                            url=url,
                            fetch_status=FetchStatus.FAILED,
                            error_message=f"Unsupported Content-Type: '{content_type}'. Must be image or HTML post.",
                            retries_used=retries,
                        )

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                retries += 1
                if retries < max_retries:
                    await asyncio.sleep(self.config.RETRY_BACKOFF_FACTOR * (2 ** (retries - 1)))
                    continue
                return CandidateFetchResult(
                    url=url,
                    fetch_status=FetchStatus.FAILED,
                    error_message=f"Network error after {retries} attempts: {e}",
                    retries_used=retries,
                )
            except Exception as e:
                return CandidateFetchResult(
                    url=url,
                    fetch_status=FetchStatus.FAILED,
                    error_message=f"Unexpected error fetching URL: {e}",
                    retries_used=retries,
                )

        return CandidateFetchResult(
            url=url,
            fetch_status=FetchStatus.FAILED,
            error_message="Exceeded maximum retries.",
            retries_used=retries,
        )

    async def _download_image_bytes(
        self, image_url: str, client: httpx.AsyncClient
    ) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """Download and validate image bytes from an extracted image URL."""
        parsed = urlparse(image_url)
        if self.config.ENABLE_SSRF_PROTECTION:
            safe, err = SSRFGuard.validate_host(parsed.hostname or "")
            if not safe:
                return None, None, f"Image URL SSRF violation: {err}"

        try:
            async with client.stream("GET", image_url) as resp:
                if resp.status_code != 200:
                    return None, None, f"HTTP {resp.status_code} fetching image."

                img_bytes, read_err = await self._read_stream(resp)
                if read_err:
                    return None, None, read_err

                valid, mime, img_err = validate_image_data(
                    img_bytes, self.config.ALLOWED_IMAGE_MIME_TYPES
                )
                if not valid:
                    return None, None, f"Invalid image format: {img_err}"

                return img_bytes, mime, None
        except Exception as e:
            return None, None, str(e)

    async def _read_stream(
        self, resp: httpx.Response, max_bytes: Optional[int] = None
    ) -> Tuple[bytes, Optional[str]]:
        """Stream response body enforcing maximum byte limit."""
        limit = max_bytes or self.config.MAX_IMAGE_SIZE_BYTES
        buf = bytearray()
        async for chunk in resp.aiter_bytes(chunk_size=16384):
            buf.extend(chunk)
            if len(buf) > limit:
                return bytes(), f"File size exceeded maximum limit of {limit / (1024 * 1024):.1f}MB."
        return bytes(buf), None

    def _is_captcha_page(self, html: str) -> bool:
        lower = html.lower()
        markers = (
            "g-recaptcha",
            "hcaptcha",
            "cf-turnstile",
            "challenge-running",
            "captcha-box",
            "security check",
        )
        return any(m in lower for m in markers)

    async def fetch_all(
        self, urls: List[str], post_extractor: Optional[PostExtractor] = None
    ) -> List[CandidateFetchResult]:
        """Fetch multiple candidate URLs concurrently bounded by semaphore."""
        async with httpx.AsyncClient(
            headers={"User-Agent": self.config.USER_AGENT},
            timeout=float(self.config.REQUEST_TIMEOUT_SECONDS),
            follow_redirects=True,
            max_redirects=self.config.MAX_REDIRECTS,
        ) as client:
            tasks = [
                self.fetch_candidate(u, post_extractor=post_extractor, client=client)
                for u in urls
            ]
            return await asyncio.gather(*tasks)
