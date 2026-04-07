"""Tests for the SSRF validator."""

import pytest
from scanners.ssrf_validator import SSRFValidator


@pytest.fixture
def validator():
    return SSRFValidator()


class TestBlockedNetworks:
    @pytest.mark.parametrize(
        "url",
        [
            "http://10.0.0.1/api",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.1.1/",
            "http://192.168.255.255/",
        ],
    )
    def test_rfc1918_blocked(self, validator, url):
        result = validator.validate_url(url, resolve_dns=False)
        assert not result.safe, f"Should block RFC 1918: {url}"

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://127.0.0.1:8080/",
            "http://127.255.255.255/",
        ],
    )
    def test_loopback_blocked(self, validator, url):
        result = validator.validate_url(url, resolve_dns=False)
        assert not result.safe, f"Should block loopback: {url}"

    def test_link_local_blocked(self, validator):
        result = validator.validate_url(
            "http://169.254.169.254/latest/meta-data/", resolve_dns=False
        )
        assert not result.safe

    def test_cgnat_blocked(self, validator):
        result = validator.validate_url("http://100.64.0.1/", resolve_dns=False)
        assert not result.safe


class TestBlockedHostnames:
    @pytest.mark.parametrize(
        "url",
        [
            "https://metadata.google.internal/computeMetadata/v1/",
            "https://metadata.goog/computeMetadata/v1/",
            "http://169.254.169.254/latest/meta-data/",
        ],
    )
    def test_cloud_metadata_blocked(self, validator, url):
        result = validator.validate_url(url, resolve_dns=False)
        assert not result.safe, f"Should block cloud metadata: {url}"


class TestBlockedSchemes:
    @pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "data", "dict", "ldap"])
    def test_dangerous_schemes_blocked(self, validator, scheme):
        result = validator.validate_url(f"{scheme}:///etc/passwd", resolve_dns=False)
        assert not result.safe, f"Should block scheme: {scheme}"


class TestSafeUrls:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/konflux-ci/fullsend",
            "https://example.com/api/data",
            "https://registry.npmjs.org/package",
            "https://pypi.org/simple/requests/",
        ],
    )
    def test_public_urls_allowed(self, validator, url):
        result = validator.validate_url(url, resolve_dns=False)
        assert result.safe, f"Should allow public URL: {url}"


class TestRedirectChain:
    def test_safe_chain(self, validator):
        chain = [
            "https://example.com/page1",
            "https://example.com/page2",
        ]
        result = validator.validate_redirect_chain(chain)
        assert result.safe

    def test_chain_with_internal_hop(self, validator):
        chain = [
            "https://example.com/redirect",
            "http://192.168.1.100/internal",
        ]
        result = validator.validate_redirect_chain(chain)
        assert not result.safe
        assert "hop 1" in result.reason.lower()


class TestMalformedUrls:
    def test_empty_hostname(self, validator):
        result = validator.validate_url("http:///path", resolve_dns=False)
        assert not result.safe

    def test_no_scheme(self, validator):
        result = validator.validate_url("not-a-url", resolve_dns=False)
        assert not result.safe


class TestCustomConfig:
    def test_extra_blocked_hosts(self):
        v = SSRFValidator(extra_blocked_hosts={"evil.internal.corp"})
        result = v.validate_url("https://evil.internal.corp/api", resolve_dns=False)
        assert not result.safe

    def test_extra_blocked_networks(self):
        v = SSRFValidator(extra_blocked_networks=["203.0.113.0/24"])
        result = v.validate_url("http://203.0.113.50/", resolve_dns=False)
        assert not result.safe
