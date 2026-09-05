"""
Security hardening for Module 2: Claimed-Profile Verification (v2).
Provides:
- SSRFGuard: Multi-layer IP resolution and private/loopback/cloud-metadata blocking.
- DomainPolicy: Enforces domain allowlist and denylist.
- URLSanitizer: Schema validation, credential stripping, and URL normalization.
- SecretScanner: Static scan verifying absence of hardcoded credentials.
"""

import ipaddress
import os
import re
import socket
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse, urlunparse

from .exceptions import SSRFSecurityError


class SSRFGuard:
    """
    Guards against Server-Side Request Forgery (SSRF).
    Resolves hostnames to IP addresses and rejects private, loopback,
    link-local, cloud metadata, carrier-grade NAT, or reserved CIDR ranges.
    """

    # Prohibited CIDR blocks (IPv4 and IPv6)
    BLOCKED_CIDRS = [
        ipaddress.ip_network("127.0.0.0/8"),      # Loopback
        ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Private
        ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Private
        ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Private
        ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud Metadata (AWS/GCP/Azure)
        ipaddress.ip_network("0.0.0.0/8"),        # Current network
        ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
        ipaddress.ip_network("198.18.0.0/15"),    # Network benchmark tests
        ipaddress.ip_network("224.0.0.0/4"),      # Multicast
        ipaddress.ip_network("240.0.0.0/4"),      # Reserved
        # IPv6
        ipaddress.ip_network("::1/128"),          # Loopback
        ipaddress.ip_network("fc00::/7"),         # Unique local
        ipaddress.ip_network("fe80::/10"),        # Link-local
        ipaddress.ip_network("::/128"),           # Unspecified
    ]

    BLOCKED_HOSTS = {
        "localhost",
        "metadata.google.internal",
        "instance-data",
        "169.254.169.254",
    }

    @classmethod
    def is_ip_blocked(cls, ip_str: str) -> bool:
        """Check if an IP string falls inside any prohibited network."""
        try:
            ip = ipaddress.ip_address(ip_str)
            for cidr in cls.BLOCKED_CIDRS:
                if ip in cidr:
                    return True
            return (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            )
        except ValueError:
            return True

    @classmethod
    def validate_host(cls, hostname: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that the hostname does not resolve to an internal/private address.
        """
        if not hostname:
            return False, "Empty hostname."

        clean_host = hostname.strip().lower()
        if clean_host in cls.BLOCKED_HOSTS:
            return False, f"SSRF Guard: Prohibited hostname '{clean_host}' is blocked."

        # If hostname is a raw IP literal
        try:
            ip = ipaddress.ip_address(clean_host)
            if cls.is_ip_blocked(str(ip)):
                return False, f"SSRF Guard: Direct IP '{clean_host}' is in a restricted range."
            return True, None
        except ValueError:
            pass  # Hostname is a domain name

        # Resolve hostname via DNS
        try:
            addr_info = socket.getaddrinfo(clean_host, None)
            for item in addr_info:
                resolved_ip = item[4][0]
                if cls.is_ip_blocked(resolved_ip):
                    return False, (
                        f"SSRF Guard: Host '{clean_host}' resolved to prohibited IP '{resolved_ip}'."
                    )
            return True, None
        except socket.gaierror:
            return False, f"DNS resolution failed for hostname '{clean_host}'."
        except Exception as e:
            return False, f"Error validating host '{clean_host}': {e}"


class DomainPolicy:
    """
    Enforces optional domain allowlists and denylists.
    """

    def __init__(
        self,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
    ):
        self.allowlist: Optional[Set[str]] = (
            {d.strip().lower() for d in allowlist if d.strip()} if allowlist else None
        )
        self.denylist: Set[str] = (
            {d.strip().lower() for d in denylist if d.strip()} if denylist else set()
        )

    def is_domain_allowed(self, hostname: str) -> Tuple[bool, Optional[str]]:
        """Check whether hostname passes domain policies."""
        if not hostname:
            return False, "Missing hostname."

        host = hostname.strip().lower()

        # Check denylist first
        for denied in self.denylist:
            if host == denied or host.endswith("." + denied):
                return False, f"Domain Policy: Domain '{host}' is in the denylist."

        # Check allowlist if configured
        if self.allowlist is not None:
            allowed = False
            for allowed_domain in self.allowlist:
                if host == allowed_domain or host.endswith("." + allowed_domain):
                    allowed = True
                    break
            if not allowed:
                return False, f"Domain Policy: Domain '{host}' is not in the allowlist."

        return True, None


class URLSanitizer:
    """
    Validates, strips credentials from, and normalizes candidate URLs.
    """

    MAX_URL_LENGTH = 2048

    @classmethod
    def sanitize(
        cls,
        url: str,
        enforce_https: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate and sanitize URL:
        - Checks URL length.
        - Enforces allowed schemes (https, or http if enforce_https=False).
        - Strips user:pass credentials if embedded.
        - Strips URL fragments (#hash).
        - Normalizes host and path.
        Returns: (is_valid, sanitized_url, error_message).
        """
        if not url or not isinstance(url, str):
            return False, None, "URL must be a non-empty string."

        clean_url = url.strip()
        if len(clean_url) > cls.MAX_URL_LENGTH:
            return False, None, f"URL exceeds maximum length of {cls.MAX_URL_LENGTH} characters."

        parsed = urlparse(clean_url)
        allowed_schemes = ("https",) if enforce_https else ("https", "http")
        if parsed.scheme.lower() not in allowed_schemes:
            return False, None, (
                f"Invalid URL scheme '{parsed.scheme}'. Permitted schemes: {allowed_schemes}."
            )

        if not parsed.hostname:
            return False, None, "URL missing valid hostname."

        # Reject or strip embedded credentials (http://user:pass@example.com)
        if parsed.username or parsed.password:
            return False, None, "URLs with embedded credentials (user:password@) are prohibited."

        # Reconstruct normalized URL without fragments
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "",  # strip fragment
        ))

        return True, normalized, None


class SecretScanner:
    """
    Static secret scanner to confirm no hardcoded API keys or credentials
    exist in the repository source code.
    """

    SUSPICIOUS_PATTERNS = [
        re.compile(r"""(?:api[_-]?key|secret[_-]?key|auth[_-]?token|password)\s*[:=]\s*["'][A-Za-z0-9_\-]{20,}["']""", re.IGNORECASE),
        re.compile(r"""-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"""),
        re.compile(r"""ghp_[A-Za-z0-9]{36}"""),  # GitHub token
        re.compile(r"""AIza[0-9A-Za-z-_]{35}"""),  # Google API key
    ]

    @classmethod
    def scan_directory(cls, directory_path: str) -> List[Tuple[str, int, str]]:
        """
        Scan all python files in directory for hardcoded secrets.
        Returns list of (file_path, line_number, snippet) for detected secrets.
        """
        findings = []
        for root, _, files in os.walk(directory_path):
            if any(p in root for p in (".git", ".venv", "__pycache__", "temp")):
                continue
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            for lineno, line in enumerate(f, 1):
                                for pattern in cls.SUSPICIOUS_PATTERNS:
                                    if pattern.search(line):
                                        findings.append((full_path, lineno, line.strip()[:60]))
                    except OSError:
                        continue
        return findings
