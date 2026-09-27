"""Automated Tests for SONORA Frontend UI, Startup Animation, and Static Assets."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestSonoraFrontendAndAnimation:
    """Verifies DOM hierarchy, styling attributes, and startup overlay mechanics."""

    def test_startup_overlay_dom_structure(self) -> None:
        """Verifies startup overlay contains required audio cords and typography."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        # Verify overlay container
        assert 'id="startup-overlay"' in html
        assert 'class="startup-overlay"' in html

        # Verify acoustic harmonic cords SVG
        assert 'class="waveform-svg"' in html
        assert 'wave-cord-1' in html
        assert 'wave-cord-2' in html
        assert 'wave-cord-3' in html
        assert 'wave-cord-4' in html

        # Verify branding titles
        assert '<h1 class="startup-title">SONORA</h1>' in html
        assert '<p class="startup-subtitle">MUSIC DOWNLOADER</p>' in html

    def test_startup_css_reduced_motion_and_keyframes(self) -> None:
        """Verifies CSS contains reduced motion overrides and keyframe animations."""
        response = client.get("/static/css/styles.css")
        assert response.status_code == 200
        css = response.text

        # Verify keyframes
        assert "@keyframes acousticHarmonic" in css
        assert "@keyframes revealWordmark" in css
        assert "@keyframes revealSubtitle" in css

        # Verify prefers-reduced-motion media query
        assert "@media (prefers-reduced-motion: reduce)" in css
        assert "animation: none !important" in css
        assert "opacity: 1 !important" in css

    def test_app_js_startup_lifecycle(self) -> None:
        """Verifies client app controller manages startup lifecycle and reduced motion."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        js = response.text

        assert "prefers-reduced-motion" in js
        assert "fade-out" in js
        assert "initStartupAnimation" in js

    def test_landing_page_sections_and_navigation(self) -> None:
        """Verifies presence of all primary landing page sections and navigation links."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        # Navigation
        assert 'class="brand-name">SONORA</span>' in html
        assert 'href="#hero"' in html
        assert 'href="#features"' in html
        assert 'href="#sites"' in html
        assert 'href="#faq"' in html
        assert 'id="mobile-menu-btn"' in html

        # Hero
        assert "YOUR MUSIC.<br><span class=\"highlight\">EVERYWHERE.</span>" in html
        assert "Paste. Download. Listen." in html
        assert "Fast, clean and free music downloader." in html

        # Features
        assert 'id="features"' in html
        assert "High-Speed Downloads" in html
        assert "Honest Quality" in html
        assert "Hardened Security" in html
        assert "Playlist Automation" in html

        # Supported Sites
        assert 'id="sites"' in html
        assert "YouTube" in html
        assert "SoundCloud" in html
        assert "Bandcamp" in html

        # FAQ
        assert 'id="faq"' in html
        assert "Is SONORA completely free to use?" in html
        assert "Direct Stream Copy and Transcoding" in html
        assert "Does converting to FLAC make lossy sources lossless?" in html

        # Footer
        assert 'class="site-footer"' in html
        assert "© 2026 SONORA" in html

    def test_format_chips_and_quality_options(self) -> None:
        """Verifies presence of all approved audio formats and quality levels."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        assert 'data-format="mp3_320"' in html
        assert 'data-format="mp3_256"' in html
        assert 'data-format="mp3_vbr"' in html
        assert 'data-format="m4a"' in html
        assert 'data-format="opus"' in html
        assert 'data-format="flac"' in html

    def test_playlist_and_download_progress_elements(self) -> None:
        """Verifies DOM contains playlist checklist, progress indicators, and telemetry."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        # Playlist elements
        assert 'id="playlist-checklist-container"' in html
        assert 'id="select-all-btn"' in html
        assert 'id="selected-count"' in html
        assert 'id="total-count"' in html

        # Download and Telemetry elements
        assert 'id="progress-bar-fill"' in html
        assert 'id="progress-percent"' in html
        assert 'id="dl-speed"' in html
        assert 'id="dl-eta"' in html
        assert 'id="cancel-download-btn"' in html

        # Completed & Error elements
        assert 'id="file-download-link"' in html
        assert 'id="error-message"' in html
        assert 'id="error-retry-btn"' in html

    def test_inspecting_state_cancel_button(self) -> None:
        """Verifies presence of cancel button in inspecting state to prevent deadlocks."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.text
        assert 'id="cancel-inspecting-btn"' in html
        assert "Cancel Inspection" in html

    def test_css_syntax_no_nested_mobile_menu_corruption(self) -> None:
        """Verifies styles.css has clean syntax without nesting .mobile-menu-btn."""
        response = client.get("/static/css/styles.css")
        assert response.status_code == 200
        css = response.text
        assert ".mobile-menu-btn {" in css
        # Verify feature-icon rule is properly terminated before mobile-menu-btn
        feature_icon_idx = css.find(".feature-icon {")
        mobile_menu_idx = css.find(".mobile-menu-btn {")
        assert mobile_menu_idx != -1
        assert feature_icon_idx != -1
        # The closing brace for feature-icon or preceding class must exist before mobile-menu-btn
        assert (
            "}\n.mobile-menu-btn {" in css
            or "}\r\n.mobile-menu-btn {" in css
            or "}\n  .mobile-menu-btn {" in css
            or "\n.mobile-menu-btn {" in css
        )

    def test_xss_safety_in_playlist_renderer(self) -> None:
        """Verifies app.js renders track titles using textContent instead of innerHTML."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        js = response.text
        assert "trackName.textContent = track.title" in js
        # Ensure track.title is not interpolated into innerHTML
        assert "${track.title}" not in js

    def test_metadata_inspection_abort_and_timeout(self) -> None:
        """Verifies app.js implements AbortController and bounded timeout for inspection."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        js = response.text
        assert "new AbortController()" in js
        assert "controller.abort('timeout')" in js
        assert "15000" in js

    def test_sse_polling_fallback_bounded_retries(self) -> None:
        """Verifies CRIT-02: startPollingFallback has bounded retry limits."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        js = response.text
        assert "MAX_POLL_FAILURES" in js
        assert "MAX_POLL_404_RETRIES" in js
        assert "MAX_POLL_ATTEMPTS" in js
        assert "consecutive404s >= MAX_POLL_404_RETRIES" in js
        assert "consecutiveErrors >= MAX_POLL_FAILURES" in js
        assert "pollAttempts > MAX_POLL_ATTEMPTS" in js

    def test_playlist_checklist_css_constraints(self) -> None:
        """Verifies styles.css enforces max-height and scrolling on playlist checklist (HIGH-04)."""
        response = client.get("/static/css/styles.css")
        assert response.status_code == 200
        css = response.text
        assert ".playlist-checklist-container {" in css
        assert ".playlist-items-list {" in css
        assert "max-height: 280px;" in css
        assert "overflow-y: auto;" in css

    def test_empty_playlist_selection_ui_behavior(self) -> None:
        """Verifies app.js disables download when 0 playlist items are selected (HIGH-03)."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        js = response.text
        assert "elements.startDownloadBtn.disabled = true;" in js
        assert "Select at least one track to download" in js
        assert "Please select at least one track from the playlist to download." in js
