"""SSRF protection adapted from Hermes Agent's URL validation.

Validates URLs against RFC 1918 private networks, cloud metadata endpoints,
link-local, CGNAT, loopback, and reserved ranges. Re-validates redirect chains.

Usage:
    validator = SSRFValidator()
    is_safe, reason = validator.validate_url("https://example.com")
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class SSRFResult:
    safe: bool
    reason: str
    resolved_ip: str | None = None


# Blocked hostname patterns (cloud metadata services)
_BLOCKED_HOSTNAMES: set[str] = {
    "metadata.google.internal",
    "metadata.goog",
    "169.254.169.254",  # AWS/GCP/Azure metadata
    "100.100.100.200",  # Alibaba Cloud metadata
    "fd00:ec2::254",  # AWS IPv6 metadata
}

# Blocked IP networks
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    # RFC 1918 private networks
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    # Loopback
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv6Network("::1/128"),
    # Link-local
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv6Network("fe80::/10"),
    # CGNAT / shared address space (RFC 6598) — Tailscale, WireGuard
    ipaddress.IPv4Network("100.64.0.0/10"),
    # Reserved / documentation
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
    # Multicast
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv6Network("ff00::/8"),
    # Unspecified
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv6Network("::/128"),
    # Unique local (IPv6 RFC 4193)
    ipaddress.IPv6Network("fc00::/7"),
]

# Blocked URL schemes
_BLOCKED_SCHEMES: set[str] = {"file", "ftp", "gopher", "data", "dict", "ldap", "tftp"}


class SSRFValidator:
    def __init__(
        self,
        extra_blocked_hosts: set[str] | None = None,
        extra_blocked_networks: list[str] | None = None,
        allowed_schemes: set[str] | None = None,
    ):
        self._blocked_hosts = _BLOCKED_HOSTNAMES.copy()
        if extra_blocked_hosts:
            self._blocked_hosts |= extra_blocked_hosts

        self._blocked_networks = _BLOCKED_NETWORKS.copy()
        if extra_blocked_networks:
            self._blocked_networks.extend(
                ipaddress.ip_network(n, strict=False) for n in extra_blocked_networks
            )

        self._allowed_schemes = allowed_schemes or {"http", "https"}

    def _check_ip(self, ip_str: str) -> SSRFResult | None:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None

        for network in self._blocked_networks:
            if ip in network:
                return SSRFResult(
                    safe=False,
                    reason=f"IP {ip} is in blocked network {network}",
                    resolved_ip=ip_str,
                )

        if ip.is_private:
            return SSRFResult(
                safe=False,
                reason=f"IP {ip} is a private address",
                resolved_ip=ip_str,
            )

        return None

    def validate_url(self, url: str, resolve_dns: bool = True) -> SSRFResult:
        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            return SSRFResult(safe=False, reason="Malformed URL")

        # Check scheme
        scheme = (parsed.scheme or "").lower()
        if scheme in _BLOCKED_SCHEMES:
            return SSRFResult(safe=False, reason=f"Blocked scheme: {scheme}")
        if scheme not in self._allowed_schemes:
            return SSRFResult(safe=False, reason=f"Disallowed scheme: {scheme}")

        # Check hostname
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            return SSRFResult(safe=False, reason="No hostname in URL")

        # Check against blocked hostnames
        if hostname in self._blocked_hosts:
            return SSRFResult(safe=False, reason=f"Blocked hostname: {hostname}")

        # Check if hostname is a raw IP
        ip_result = self._check_ip(hostname)
        if ip_result is not None:
            return ip_result

        # DNS resolution check (fail-closed)
        if resolve_dns:
            try:
                addrs = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
            except socket.gaierror:
                return SSRFResult(
                    safe=False,
                    reason=f"DNS resolution failed for {hostname} (fail-closed)",
                )

            for _family, _, _, _, sockaddr in addrs:
                ip_str = str(sockaddr[0])
                ip_result = self._check_ip(ip_str)
                if ip_result is not None:
                    ip_result.reason = (
                        f"DNS for {hostname} resolved to blocked IP: {ip_result.reason}"
                    )
                    return ip_result

            resolved = str(addrs[0][4][0]) if addrs else None
            return SSRFResult(safe=True, reason="URL passed all checks", resolved_ip=resolved)

        return SSRFResult(safe=True, reason="URL passed all checks (DNS not resolved)")

    def validate_redirect_chain(self, urls: list[str]) -> SSRFResult:
        for i, url in enumerate(urls):
            result = self.validate_url(url)
            if not result.safe:
                result.reason = f"Redirect hop {i}: {result.reason}"
                return result
        return SSRFResult(safe=True, reason=f"All {len(urls)} redirect hops passed")


if __name__ == "__main__":
    test_urls = [
        "https://example.com/api/data",
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "http://192.168.1.1/admin",
        "http://10.0.0.1:8080/internal",
        "file:///etc/passwd",
        "https://100.64.0.1/tailscale-api",
        "http://127.0.0.1:3000/",
        "gopher://evil.com/",
        "https://github.com/konflux-ci/fullsend",
    ]

    validator = SSRFValidator()
    for url in test_urls:
        result = validator.validate_url(url, resolve_dns=False)
        status = "SAFE" if result.safe else "BLOCKED"
        print(f"  {status:<8} {url}")
        if not result.safe:
            print(f"           -> {result.reason}")
