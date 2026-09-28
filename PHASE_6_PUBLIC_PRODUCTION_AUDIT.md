# SONORA — Phase 6 Public Web & Production Readiness Audit
## Comprehensive Production, SEO, Security, and Observability Audit

**Audit Date:** 2026-09-28  
**Baseline Commit:** `6e9848e` (`feat: complete phase 5 media library features`)  
**Scope:** Public Web Exposure, Google Search Indexability, Security Headers, Public/Private Boundaries, Health/Observability, Containerization, and CI/CD.  

---

### 1. Executive Summary

SONORA is transitioning from a private self-hosted utility into a **production-ready, publicly deployable web application** discoverable on Google Search. This transition requires strict adherence to search engine guidelines, zero-trust security boundaries, robust observability, truthful metadata, and resilient containerized deployment.

This audit evaluates the current codebase against 12 core production pillars and defines the concrete architectural plan for Phase 6.

---

### 2. Detailed Pillar-by-Pillar Audit

#### Pillar 1: Public vs. Private Route Classification & Boundary Isolation
- **Current State:** The root route `/` serves `app/static/index.html`. API endpoints are mounted under `/api/v1/`. Completed files are downloaded via `/api/v1/downloads/{job_id}/file`.
- **Findings:**
  - Search crawlers could theoretically attempt to crawl API endpoints if links appear anywhere or are inferred.
  - Job UUIDs and download URLs must have explicit `X-Robots-Tag: noindex, nofollow, noarchive` headers.
  - The SQLite database and completed downloads must never be indexed or listed in public sitemaps.
- **Remediation Plan:**
  - Add `X-Robots-Tag` middleware / response headers on all `/api/*` and `/static/` internal assets.
  - Add `/robots.txt` explicitly disallowing `/api/` and internal directories while allowing `/` and public assets.

#### Pillar 2: Google Search Discoverability & Crawlability
- **Current State:** `app/static/index.html` has basic `<title>` and `<meta name="description">` tags.
- **Findings:**
  - Missing canonical URL (`<link rel="canonical" href="...">`).
  - Missing Open Graph (`og:title`, `og:description`, `og:type`, `og:url`, `og:image`, `og:site_name`) and Twitter Card meta tags.
  - Googlebot requires core descriptive content to be available in the initial HTML DOM rather than rendered solely via client-side JavaScript.
- **Remediation Plan:**
  - Add complete Open Graph, Twitter cards, and canonical links in `<head>`.
  - Add structured, crawlable public sections in the initial HTML: *How It Works*, *Download Profiles Showcase*, *Audio Fidelity Guide*, *Trust & Privacy Pillars*, and *FAQ*.

#### Pillar 3: Truthful Structured Data (JSON-LD)
- **Current State:** No JSON-LD structured data is present.
- **Findings:**
  - To enhance search engine understanding without violating Google Search spam policies, only truthful, representative structured data should be embedded.
  - `SoftwareApplication` and `WebSite` schemas accurately represent the SONORA music downloader. No fake reviews, ratings, or misleading price claims should be generated.
- **Remediation Plan:**
  - Embed valid, tested JSON-LD `@graph` containing `SoftwareApplication` and `WebSite` schemas.

#### Pillar 4: Robots.txt & XML Sitemap Endpoints
- **Current State:** No dedicated `/robots.txt` or `/sitemap.xml` endpoints exist.
- **Findings:**
  - Crawlers expect `/robots.txt` at the domain root with a reference to `/sitemap.xml`.
  - The sitemap must be dynamically or statically served as valid XML (`application/xml`), referencing only canonical public URLs (`/`, `/privacy`, `/terms`).
- **Remediation Plan:**
  - Implement `/robots.txt` and `/sitemap.xml` routes in `app/main.py`.

#### Pillar 5: Security Headers for Public HTTPS Exposure
- **Current State:** FastAPI serves responses with standard headers; no custom security headers middleware is registered.
- **Findings:**
  - Public exposure requires defense-in-depth against MIME sniffing, clickjacking, and cross-site embedding.
- **Remediation Plan:**
  - Implement security middleware injecting:
    - `X-Content-Type-Options: nosniff`
    - `X-Frame-Options: DENY`
    - `Referrer-Policy: strict-origin-when-cross-origin`
    - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
    - `Cross-Origin-Opener-Policy: same-origin`

#### Pillar 6: Legal, Trust, and User Safety
- **Current State:** Basic FAQ exists; no formal Privacy Policy, Terms of Service, or DMCA/Copyright notice is present.
- **Findings:**
  - Public media utilities require clear acceptable use guidance, copyright notices, and privacy statements emphasizing local processing and automatic temp storage cleanup.
- **Remediation Plan:**
  - Add accessible modal dialogs and dedicated routes/sections for Terms of Service, Privacy Policy, and DMCA Copyright Guidance.

#### Pillar 7: Production Health Checks & Observability
- **Current State:** No standardized `/healthz` or `/readyz` endpoints exist.
- **Findings:**
  - Container orchestrators (Docker, Kubernetes, AWS ECS, Fly.io) require lightweight liveness (`/healthz`) and readiness (`/readyz`) probes.
  - Readiness should verify database connectivity, disk storage threshold, worker pool state, and external tool binaries (FFmpeg, yt-dlp) without leaking internal paths.
- **Remediation Plan:**
  - Implement `/healthz` (200 OK fast ping) and `/readyz` (component health check).

#### Pillar 8: Containerization & Deployment
- **Current State:** No `Dockerfile` or `.dockerignore` exists.
- **Findings:**
  - Production deployment requires a standardized container with Python 3.12, system FFmpeg, a non-root runtime user, volume persistence for `data/`, and sensible entrypoint configuration.
- **Remediation Plan:**
  - Create multi-stage `Dockerfile`, `.dockerignore`, and `docker-compose.yml`.

#### Pillar 9: CI/CD Automation
- **Current State:** No GitHub Actions workflow exists in `.github/workflows/`.
- **Findings:**
  - Automated continuous integration is needed to enforce Ruff linting and pytest test execution on every commit and pull request.
- **Remediation Plan:**
  - Create `.github/workflows/ci.yml`.

#### Pillar 10: Performance & Core Web Vitals
- **Current State:** Clean vanilla HTML/CSS/JS with no heavy frameworks.
- **Findings:**
  - Ensure fonts use `preconnect` and `display=swap`.
  - Ensure responsive layout maintains zero Cumulative Layout Shift (CLS) with predefined container dimensions.

#### Pillar 11: Accessibility (WCAG 2.1 AA)
- **Current State:** Strong base from Phase 4/5 (ARIA roles, live regions, focus styles, keyboard navigation).
- **Findings:**
  - Extend modal focus trapping and keyboard dismissal to new legal and help dialogs.

#### Pillar 12: Regression Testing Strategy
- **Current State:** 128 tests passing across existing feature suites.
- **Findings:**
  - Add dedicated `tests/test_production_readiness.py` covering SEO tags, sitemap, robots, security headers, health checks, and legal routes.

---

### 3. Conclusion & Execution Plan

All 12 pillars will be implemented in structured, surgical batches following the verified baseline.
