"""
Tests for security hardening (SSRFGuard, DomainPolicy, URLSanitizer, SecretScanner).
Module 2: Claimed-Profile Verification (v2).
"""

import os
import pytest

from member2_verify.security import (
    DomainPolicy,
    SSRFGuard,
    SecretScanner,
    URLSanitizer,
)


def test_ssrf_guard_blocks_private_and_loopback():
    """Verify SSRFGuard blocks loopback, private IPv4, and cloud metadata."""
    blocked_ips = [
        "127.0.0.1",
        "127.0.0.100",
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # AWS/Azure/GCP metadata
        "::1",              # IPv6 loopback
        "fe80::1",          # IPv6 link-local
    ]
    for ip in blocked_ips:
        assert SSRFGuard.is_ip_blocked(ip) is True, f"Failed to block {ip}"

    # Public IP should not be blocked
    assert SSRFGuard.is_ip_blocked("8.8.8.8") is False
    assert SSRFGuard.is_ip_blocked("1.1.1.1") is False


def test_ssrf_guard_blocks_prohibited_hosts():
    """Verify SSRFGuard blocks prohibited hostnames."""
    is_safe, err = SSRFGuard.validate_host("localhost")
    assert is_safe is False
    assert "blocked" in err.lower()

    is_safe, err = SSRFGuard.validate_host("metadata.google.internal")
    assert is_safe is False

    is_safe, err = SSRFGuard.validate_host("169.254.169.254")
    assert is_safe is False


def test_domain_policy_allowlist():
    """Verify DomainPolicy allows only domains in allowlist."""
    policy = DomainPolicy(allowlist=["example.com", "instagram.com"])

    allowed, _ = policy.is_domain_allowed("example.com")
    assert allowed is True

    allowed, _ = policy.is_domain_allowed("cdn.example.com")
    assert allowed is True

    allowed, err = policy.is_domain_allowed("untrusted.org")
    assert allowed is False
    assert "not in the allowlist" in err


def test_domain_policy_denylist():
    """Verify DomainPolicy rejects domains in denylist."""
    policy = DomainPolicy(denylist=["evil.com", "phishing.net"])

    allowed, err = policy.is_domain_allowed("evil.com")
    assert allowed is False
    assert "denylist" in err

    allowed, err = policy.is_domain_allowed("sub.evil.com")
    assert allowed is False

    allowed, _ = policy.is_domain_allowed("safe-site.com")
    assert allowed is True


def test_url_sanitizer_rejects_credentials():
    """Verify URLSanitizer blocks URLs with user:pass."""
    is_valid, _, err = URLSanitizer.sanitize("https://alice:secretpass@example.com/photo.jpg")
    assert is_valid is False
    assert "embedded credentials" in err


def test_url_sanitizer_length_and_fragment_stripping():
    """Verify URL length check and fragment removal."""
    # Length check
    giant_url = "https://example.com/" + "a" * 2500
    is_valid, _, err = URLSanitizer.sanitize(giant_url)
    assert is_valid is False
    assert "maximum length" in err

    # Fragment stripping
    is_valid, clean_url, _ = URLSanitizer.sanitize("https://example.com/photo.jpg#profile-header")
    assert is_valid is True
    assert clean_url == "https://example.com/photo.jpg"


def test_secret_scanner_repo_check():
    """
    CI Secret Scan: verifies no hardcoded secrets or private keys exist
    in the member2_verify package source.
    """
    package_dir = os.path.join(os.path.dirname(__file__), "..", "member2_verify")
    findings = SecretScanner.scan_directory(package_dir)
    assert len(findings) == 0, f"Found hardcoded secrets in source files: {findings}"
