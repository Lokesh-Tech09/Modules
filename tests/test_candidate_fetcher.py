"""
Tests for CandidateFetcher (Module 2: Claimed-Profile Verification v2).
Tests async fetching, bounded concurrency, retries, circuit breaker, and SSRF.
"""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest

from member2_verify.candidate_fetcher import CandidateFetcher, DomainCircuitBreaker
from member2_verify.config import VerificationConfig
from member2_verify.models import FetchStatus


def create_dummy_jpeg_bytes() -> bytes:
    """Helper to create valid JPEG byte data."""
    img = Image.new("RGB", (100, 100), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def custom_config(tmp_path):
    return VerificationConfig(
        REQUEST_TIMEOUT_SECONDS=2,
        MAX_IMAGE_SIZE_BYTES=1024 * 1024,
        TEMP_DIR=str(tmp_path / "temp"),
        ENABLE_SSRF_PROTECTION=True,
        RESPECT_ROBOTS_TXT=False,
        MAX_RETRIES=2,
        RETRY_BACKOFF_FACTOR=0.01,
        CIRCUIT_BREAKER_THRESHOLD=2,
        CIRCUIT_BREAKER_RESET_TIMEOUT=1.0,
    )


@pytest.fixture
def fetcher(custom_config):
    return CandidateFetcher(config=custom_config)


@pytest.mark.asyncio
async def test_fetch_direct_image_success(fetcher):
    """Test fetching a direct JPEG image URL asynchronously."""
    img_bytes = create_dummy_jpeg_bytes()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = MagicMock(path="/photos/me.jpg")
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.aiter_bytes = MagicMock(return_value=_async_iter([img_bytes]))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)

    with patch("member2_verify.candidate_fetcher.SSRFGuard.validate_host", return_value=(True, None)):
        result = await fetcher.fetch_candidate("https://example.com/photos/me.jpg", client=mock_client)

        assert result.fetch_status == FetchStatus.SUCCESS
        assert result.content_type == "image/jpeg"
        assert result.image_bytes == img_bytes
        assert result.local_image_path is not None


@pytest.mark.asyncio
async def test_ssrf_blocking_loopback(fetcher):
    """Test that candidate URLs pointing to localhost/loopback are rejected."""
    result = await fetcher.fetch_candidate("http://127.0.0.1/profile.jpg")
    assert result.fetch_status == FetchStatus.FAILED
    assert "SSRF" in result.error_message


@pytest.mark.asyncio
async def test_ssrf_blocking_private_network(fetcher):
    """Test that candidate URLs pointing to internal RFC1918 IPs are rejected."""
    result = await fetcher.fetch_candidate("http://192.168.1.50/photo.jpg")
    assert result.fetch_status == FetchStatus.FAILED
    assert "SSRF" in result.error_message


@pytest.mark.asyncio
async def test_fetch_access_restricted_403_blocked(fetcher):
    """Test that 403 Forbidden is marked BLOCKED."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.headers = {}
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)

    with patch("member2_verify.candidate_fetcher.SSRFGuard.validate_host", return_value=(True, None)):
        result = await fetcher.fetch_candidate("https://example.com/private/profile", client=mock_client)
        assert result.fetch_status == FetchStatus.BLOCKED
        assert "Access restricted" in result.error_message


@pytest.mark.asyncio
async def test_fetch_captcha_detected_blocked(fetcher):
    """Test that pages presenting CAPTCHAs are marked BLOCKED."""
    captcha_html = b"<html><body><div class='g-recaptcha'></div>Security check</body></html>"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = MagicMock(path="/protected")
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.encoding = "utf-8"
    mock_resp.aiter_bytes = MagicMock(return_value=_async_iter([captcha_html]))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)

    with patch("member2_verify.candidate_fetcher.SSRFGuard.validate_host", return_value=(True, None)):
        result = await fetcher.fetch_candidate("https://example.com/protected", client=mock_client)
        assert result.fetch_status == FetchStatus.BLOCKED
        assert "CAPTCHA" in result.error_message


@pytest.mark.asyncio
async def test_circuit_breaker_tripping(fetcher):
    """Verify circuit breaker trips and short-circuits after consecutive failures."""
    domain = "failing-host.org"
    url = f"https://{domain}/photo.jpg"

    # Fail threshold times
    fetcher.circuit_breaker.record_failure(domain)
    fetcher.circuit_breaker.record_failure(domain)

    # Breaker should now be OPEN
    assert fetcher.circuit_breaker.is_available(domain) is False

    with patch("member2_verify.candidate_fetcher.SSRFGuard.validate_host", return_value=(True, None)):
        result = await fetcher.fetch_candidate(url)
        assert result.fetch_status == FetchStatus.FAILED
        assert "Circuit breaker is OPEN" in result.error_message


@pytest.mark.asyncio
async def test_bounded_concurrency(fetcher):
    """Verify bounded concurrency semaphore processes list concurrently."""
    img_bytes = create_dummy_jpeg_bytes()

    async def mock_fetch_cand(url, **kwargs):
        from member2_verify.models import CandidateFetchResult, FetchStatus
        await asyncio.sleep(0.02)
        return CandidateFetchResult(
            url=url,
            fetch_status=FetchStatus.SUCCESS,
            content_type="image/jpeg",
            image_bytes=img_bytes,
        )

    with patch.object(fetcher, "fetch_candidate", side_effect=mock_fetch_cand):
        urls = [f"https://example.com/photo_{i}.jpg" for i in range(10)]
        results = await fetcher.fetch_all(urls)
        assert len(results) == 10
        assert all(r.fetch_status == FetchStatus.SUCCESS for r in results)


async def _async_iter(items):
    for item in items:
        yield item
