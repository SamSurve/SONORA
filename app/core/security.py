"""Auralis Multi-Layer Security & Deep SSRF Protection Engine.

Implements pre-flight DNS resolution, comprehensive IPv4/IPv6 CIDR blacklisting,
obfuscated IP detection, internal domain blocking, DNS rebinding mitigation,
and redirect re-validation.
"""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse


class SecurityException(Exception):
    """Base exception for security boundary violations."""


class SSRFSecurityException(SecurityException):
    """Raised when an address or target resolves to a forbidden internal/private network."""


class InvalidURLException(SecurityException):
    """Raised when a URL is malformed, has an unapproved protocol, or contains obfuscated IP."""


# ==============================================================================
# Comprehensive CIDR Blacklists (IPv4 & IPv6)
# ==============================================================================

BLOCKED_IPV4_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # Current network (only valid as source address)
    ipaddress.ip_network("10.0.0.0/8"),  # Private network RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-Grade NAT RFC 6598
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback RFC 1122
    ipaddress.ip_network("169.254.0.0/16"),  # Link-Local (APIPA / Cloud metadata services)
    ipaddress.ip_network("172.16.0.0/12"),  # Private network RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1 documentation
    ipaddress.ip_network("192.168.0.0/16"),  # Private network RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),  # Network benchmark testing RFC 2544
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2 documentation
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3 documentation
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast RFC 5771
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved for future use RFC 1112
    ipaddress.ip_network("255.255.255.255/32"),  # Limited Broadcast
]

BLOCKED_IPV6_NETWORKS = [
    ipaddress.ip_network("::/128"),  # Unspecified address RFC 4291
    ipaddress.ip_network("::1/128"),  # Loopback RFC 4291
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6 addresses (unwrapped & verified)
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation RFC 6052
    ipaddress.ip_network("100::/64"),  # Discard-only prefix RFC 6666
    ipaddress.ip_network("2001:db8::/32"),  # Documentation RFC 3849
    ipaddress.ip_network("fc00::/7"),  # Unique Local Address (ULA / Private) RFC 4193
    ipaddress.ip_network("fe80::/10"),  # Link-Local RFC 4291
    ipaddress.ip_network("fec0::/10"),  # Site-Local (deprecated) RFC 3879
    ipaddress.ip_network("ff00::/8"),  # Multicast RFC 4291
]

FORBIDDEN_HOSTNAMES_REGEX = re.compile(
    r"^(localhost|.*\.localhost|.*\.local|.*\.internal|.*\.lan|.*\.home|.*\.corp)$",
    re.IGNORECASE,
)

# Obfuscated integer formats (DWORD, Hex, Octal)
DWORD_IP_REGEX = re.compile(r"^\d+$")
HEX_IP_REGEX = re.compile(r"^0x[0-9a-fA-F]+$")
OCTAL_OCTET_REGEX = re.compile(r"^0[0-7]+$")


def is_ip_blocked(ip_addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Evaluates whether an IP address falls within any forbidden or private CIDR range."""
    # Unwrap IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip_addr, ipaddress.IPv6Address) and ip_addr.ipv4_mapped is not None:
        ip_addr = ip_addr.ipv4_mapped

    if isinstance(ip_addr, ipaddress.IPv4Address):
        return any(ip_addr in network for network in BLOCKED_IPV4_NETWORKS)
    elif isinstance(ip_addr, ipaddress.IPv6Address):
        return any(ip_addr in network for network in BLOCKED_IPV6_NETWORKS)
    return True


def check_obfuscated_ip_literal(hostname: str) -> None:
    """Detects and rejects suspicious or obfuscated IP representations (DWORD, Octal, Hex)."""
    clean_host = hostname.strip("[]")

    # 1. Single integer / DWORD (e.g., 2130706433 for 127.0.0.1)
    if DWORD_IP_REGEX.match(clean_host):
        raise SSRFSecurityException(f"Obfuscated numeric IP literal rejected: {hostname}")

    # 2. Hex notation (e.g., 0x7f000001)
    if HEX_IP_REGEX.match(clean_host):
        raise SSRFSecurityException(f"Obfuscated hexadecimal IP literal rejected: {hostname}")

    # 3. Dotted octets with octal leading zeroes or hex
    parts = clean_host.split(".")
    if len(parts) in (2, 3, 4):
        has_suspicious_part = False
        for part in parts:
            if HEX_IP_REGEX.match(part) or (OCTAL_OCTET_REGEX.match(part) and part != "0"):
                has_suspicious_part = True
                break
        if has_suspicious_part:
            raise SSRFSecurityException(f"Obfuscated octal/hex octet in IP rejected: {hostname}")


def resolve_and_validate_hostname(hostname: str, port: int = 80) -> list[str]:
    """Pre-flight DNS: resolves host to all IPs and validates every IP against CIDRs."""
    clean_host = hostname.strip("[]")

    # Check for direct IP literal first
    try:
        ip_obj = ipaddress.ip_address(clean_host)
        if is_ip_blocked(ip_obj):
            msg = f"Forbidden private/loopback IP literal detected: {clean_host}"
            raise SSRFSecurityException(msg)
        return [str(ip_obj)]
    except ValueError:
        pass  # Not a raw IP literal, proceed to hostname checks and DNS resolution

    # Block internal TLDs and localhost variants
    if FORBIDDEN_HOSTNAMES_REGEX.match(clean_host):
        raise SSRFSecurityException(f"Access to internal/local domain forbidden: {clean_host}")

    # Pre-flight DNS resolution
    try:
        addr_info = socket.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise InvalidURLException(f"Unable to resolve hostname '{clean_host}': {e}") from e

    resolved_ips: list[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if is_ip_blocked(ip_obj):
                raise SSRFSecurityException(
                    f"Domain '{clean_host}' resolved to restricted/private IP: {ip_str}"
                )
            resolved_ips.append(str(ip_obj))
        except ValueError as e:
            raise SSRFSecurityException(f"Unparseable resolved IP address '{ip_str}'") from e

    if not resolved_ips:
        raise SSRFSecurityException(f"Domain '{clean_host}' returned no valid IP addresses.")

    return resolved_ips


def validate_url(url: str, resolve_dns: bool = True) -> tuple[bool, str, list[str]]:
    """Comprehensive URL and SSRF validation.

    Args:
        url: The user-supplied URL to validate.
        resolve_dns: If True, performs pre-flight DNS resolution and CIDR check.

    Returns:
        tuple (is_valid, sanitized_url, list_of_resolved_ips)

    Raises:
        InvalidURLException: Malformed URL, unapproved protocol, or suspicious format.
        SSRFSecurityException: Targets loopback, internal networks, or restricted ranges.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLException("URL must be a non-empty string.")

    url_clean = url.strip()

    # Parse URL
    try:
        parsed = urlparse(url_clean)
    except Exception as e:
        raise InvalidURLException(f"Malformed URL structure: {e}") from e

    # 1. Scheme Check
    if parsed.scheme.lower() not in ("http", "https"):
        msg = (
            f"Unsupported protocol scheme '{parsed.scheme}'. "
            "Only http:// and https:// are permitted."
        )
        raise InvalidURLException(msg)

    # 2. Hostname Check
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLException("URL must include a valid hostname.")

    clean_host = hostname.strip("[]")
    if FORBIDDEN_HOSTNAMES_REGEX.match(clean_host):
        raise SSRFSecurityException(f"Access to internal/local domain forbidden: {clean_host}")

    # 3. Detect Obfuscated IP Literals
    check_obfuscated_ip_literal(hostname)

    # Determine Port
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    # 4. Pre-Flight DNS Resolution & CIDR Validation
    resolved_ips: list[str] = []
    if resolve_dns:
        resolved_ips = resolve_and_validate_hostname(hostname, port)

    return True, url_clean, resolved_ips


def validate_redirect(current_url: str, location_header: str) -> tuple[bool, str, list[str]]:
    """Validates an HTTP redirect target against SSRF boundaries before following."""
    if not location_header:
        raise InvalidURLException("Redirect location header is empty.")

    # Resolve relative redirects
    target_url = urljoin(current_url, location_header.strip())
    return validate_url(target_url, resolve_dns=True)
