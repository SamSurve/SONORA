"""Automated Security & SSRF Defense Test Suite."""

import socket
from unittest.mock import patch

import pytest

from app.core.security import (
    InvalidURLException,
    SSRFSecurityException,
    validate_redirect,
    validate_url,
)


class TestProtocolAndFormatValidation:
    """Tests for URL scheme and structure sanitization."""

    def test_empty_or_non_string_urls(self) -> None:
        with pytest.raises(InvalidURLException):
            validate_url("", resolve_dns=False)
        with pytest.raises(InvalidURLException):
            validate_url(None, resolve_dns=False)  # type: ignore[arg-type]

    def test_unsupported_protocols(self) -> None:
        unsupported = [
            "file:///etc/passwd",
            "file:///C:/Windows/System32/drivers/etc/hosts",
            "gopher://127.0.0.1:70/_",
            "ftp://files.example.com/music.mp3",
            "data:text/plain;base64,SGVsbG8=",
            "dict://127.0.0.1:2628/",
            "ldap://127.0.0.1:389/",
        ]
        for url in unsupported:
            with pytest.raises(InvalidURLException, match="Unsupported protocol scheme"):
                validate_url(url, resolve_dns=False)

    def test_missing_hostname(self) -> None:
        with pytest.raises(InvalidURLException, match="valid hostname"):
            validate_url("http://", resolve_dns=False)


class TestIPLiteralAndObfuscationRejection:
    """Tests detecting direct IP literals, DWORD, Octal, and Hex obfuscation."""

    def test_ipv4_loopback_literals(self) -> None:
        loopbacks = [
            "http://127.0.0.1",
            "http://127.0.0.2:8000",
            "http://127.255.255.254/secret",
        ]
        for url in loopbacks:
            with pytest.raises(SSRFSecurityException, match="Forbidden private/loopback"):
                validate_url(url, resolve_dns=True)

    def test_ipv4_private_rfc1918_literals(self) -> None:
        privates = [
            "http://10.0.0.1/",
            "http://10.254.254.1/data",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.0.1/",
            "http://192.168.1.254:3000",
        ]
        for url in privates:
            with pytest.raises(SSRFSecurityException, match="Forbidden private/loopback"):
                validate_url(url, resolve_dns=True)

    def test_ipv4_link_local_cloud_metadata(self) -> None:
        link_locals = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.0.1/",
        ]
        for url in link_locals:
            with pytest.raises(SSRFSecurityException, match="Forbidden private/loopback"):
                validate_url(url, resolve_dns=True)

    def test_carrier_grade_nat_literals(self) -> None:
        cgnats = [
            "http://100.64.0.1/",
            "http://100.127.255.254/",
        ]
        for url in cgnats:
            with pytest.raises(SSRFSecurityException, match="Forbidden private/loopback"):
                validate_url(url, resolve_dns=True)

    def test_ipv6_loopback_and_private(self) -> None:
        ipv6_blocked = [
            "http://[::1]/",
            "http://[0:0:0:0:0:0:0:1]/",
            "http://[fc00::1]/",
            "http://[fe80::1]/",
            "http://[fec0::1]/",
            "http://[::ffff:127.0.0.1]/",
        ]
        for url in ipv6_blocked:
            with pytest.raises(SSRFSecurityException, match="Forbidden private/loopback"):
                validate_url(url, resolve_dns=True)

    def test_dword_ip_obfuscation(self) -> None:
        # 2130706433 is integer decimal for 127.0.0.1
        with pytest.raises(SSRFSecurityException, match="Obfuscated numeric IP literal"):
            validate_url("http://2130706433/", resolve_dns=False)

    def test_hex_ip_obfuscation(self) -> None:
        # 0x7f000001 is hex for 127.0.0.1
        with pytest.raises(SSRFSecurityException, match="Obfuscated hexadecimal IP literal"):
            validate_url("http://0x7f000001/", resolve_dns=False)

    def test_octal_ip_obfuscation(self) -> None:
        # 0177.0.0.1 has octal 0177 for 127
        with pytest.raises(SSRFSecurityException, match="Obfuscated octal/hex octet"):
            validate_url("http://0177.0.0.1/", resolve_dns=False)


class TestInternalHostnames:
    """Tests rejecting internal domain suffixes and localhost variants."""

    def test_localhost_variants(self) -> None:
        hosts = [
            "http://localhost/",
            "http://localhost:5000/download",
            "http://sub.localhost/",
            "http://app.local/",
            "http://metadata.internal/",
            "http://printer.lan/",
            "http://nas.home/",
            "http://intranet.corp/",
        ]
        for url in hosts:
            with pytest.raises(SSRFSecurityException, match="internal/local domain forbidden"):
                validate_url(url, resolve_dns=False)


class TestDNSPreFlightAndRebinding:
    """Tests pre-flight DNS resolution and TOCTOU rebinding protection."""

    def test_domain_resolving_to_private_ip(self) -> None:
        # Simulate a domain that resolves to 10.0.0.5 or 127.0.0.1
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80)),
        ]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            with pytest.raises(SSRFSecurityException, match="resolved to restricted/private IP"):
                validate_url("http://evil-rebinding-domain.com/track", resolve_dns=True)

    def test_domain_resolving_to_mixed_ips_one_private(self) -> None:
        # If any IP in the DNS A/AAAA records is private, abort
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),  # benign
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 80)),  # private trap
        ]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            with pytest.raises(SSRFSecurityException, match="resolved to restricted/private IP"):
                validate_url("http://dual-homed-trap.com/track", resolve_dns=True)

    def test_valid_public_domain(self) -> None:
        # Mocking benign DNS response for public IP
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            valid, url, ips = validate_url(
                "https://music.youtube.com/watch?v=abc", resolve_dns=True
            )
            assert valid is True
            assert "142.250.190.46" in ips


class TestRedirectValidation:
    """Tests redirect verification against SSRF targets."""

    def test_benign_redirect(self) -> None:
        mock_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.46", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=mock_addrinfo):
            valid, target, _ = validate_redirect(
                current_url="https://youtube.com/watch?v=123",
                location_header="https://music.youtube.com/watch?v=123",
            )
            assert valid is True
            assert target == "https://music.youtube.com/watch?v=123"

    def test_redirect_to_internal_ip_aborts(self) -> None:
        with pytest.raises(SSRFSecurityException):
            validate_redirect(
                current_url="https://legitimate-service.com/track",
                location_header="http://169.254.169.254/latest/meta-data/",
            )

    def test_redirect_to_localhost_aborts(self) -> None:
        with pytest.raises(SSRFSecurityException):
            validate_redirect(
                current_url="https://legitimate-service.com/track",
                location_header="http://localhost:8080/admin",
            )
