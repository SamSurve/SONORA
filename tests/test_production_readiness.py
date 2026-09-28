"""Automated Test Suite for SONORA Production Readiness & Public Web SEO.

Verifies liveness/readiness observability probes, robots.txt, dynamic XML sitemaps,
HTTP defense-in-depth security headers, X-Robots-Tag private endpoint isolation,
JSON-LD Schema.org structured data, and legal trust endpoints.
"""

import json
import xml.etree.ElementTree as ET
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provides a FastAPI test client instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_liveness_probe(client: TestClient) -> None:
    """Verifies that /healthz returns 200 OK fast liveness response."""
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "app": "SONORA"}


def test_readyz_readiness_probe(client: TestClient) -> None:
    """Verifies that /readyz confirms database, storage, and worker health."""
    res = client.get("/readyz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "healthy"
    assert data["checks"]["storage"] == "healthy"
    assert data["checks"]["worker_pool"] in ("healthy", "unknown")


def test_robots_txt_rules_and_sitemap(client: TestClient) -> None:
    """Verifies robots.txt disallows private APIs and includes sitemap link."""
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    text = res.text

    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert "Disallow: /api/" in text
    assert "Disallow: /data/" in text
    assert f"Sitemap: {settings.CANONICAL_BASE_URL}/sitemap.xml" in text


def test_sitemap_xml_validity_and_canonical_urls(client: TestClient) -> None:
    """Verifies that sitemap.xml is valid XML containing only canonical public URLs."""
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]

    # Parse and validate XML schema
    root = ET.fromstring(res.text)
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    loc_elements = root.findall("ns:url/ns:loc", namespace)
    urls = [el.text for el in loc_elements if el.text]

    base = settings.CANONICAL_BASE_URL.rstrip("/")
    assert f"{base}/" in urls
    assert f"{base}/privacy" in urls
    assert f"{base}/terms" in urls

    # Ensure zero private API or download URLs are listed
    for url in urls:
        assert "/api/" not in url
        assert "/data/" not in url


def test_security_headers_present_on_web_responses(client: TestClient) -> None:
    """Verifies HTTP defense-in-depth security headers are injected on web requests."""
    res = client.get("/")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in headers.get("Permissions-Policy", "")
    assert headers.get("Cross-Origin-Opener-Policy") == "same-origin"


def test_private_api_endpoints_have_noindex_tag(client: TestClient) -> None:
    """Verifies that private API routes have X-Robots-Tag: noindex, nofollow."""
    res = client.get("/api/v1/profiles")
    assert res.status_code == 200
    assert "noindex" in res.headers.get("X-Robots-Tag", "")
    assert "nofollow" in res.headers.get("X-Robots-Tag", "")
    assert "noarchive" in res.headers.get("X-Robots-Tag", "")


def test_public_html_seo_and_json_ld_schema(client: TestClient) -> None:
    """Verifies HTML includes canonical, Open Graph, Twitter cards, and valid JSON-LD."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # Canonical & Meta
    assert '<link rel="canonical" href="https://sonora.app/">' in html
    assert '<meta property="og:title"' in html
    assert '<meta property="og:description"' in html
    assert '<meta name="twitter:card"' in html

    # Extract JSON-LD script and validate JSON parsing
    start_tag = '<script type="application/ld+json">'
    end_tag = "</script>"
    assert start_tag in html
    start_idx = html.find(start_tag) + len(start_tag)
    end_idx = html.find(end_tag, start_idx)
    json_ld_text = html[start_idx:end_idx].strip()

    structured_data = json.loads(json_ld_text)
    assert structured_data["@context"] == "https://schema.org"
    graph = structured_data["@graph"]
    types = [item["@type"] for item in graph]
    assert "WebSite" in types
    assert "SoftwareApplication" in types


def test_legal_routes_accessible(client: TestClient) -> None:
    """Verifies that /privacy and /terms endpoints resolve cleanly."""
    res_privacy = client.get("/privacy")
    assert res_privacy.status_code == 200

    res_terms = client.get("/terms")
    assert res_terms.status_code == 200
