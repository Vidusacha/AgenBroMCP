"""Pytest fixtures: local HTTP server and deterministic HTML/PNG test fixtures."""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
from pathlib import Path
from typing import Generator
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image, ImageDraw, ImageFont

from driver.config import DriverConfig, get_repo_root


def _load_font(size: int = 36):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def ensure_fixtures_created() -> Path:
    """Create deterministic HTML and PNG fixtures in `<repo_root>/fixtures`."""
    fixtures_dir = get_repo_root() / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create logo.png with clear text "LOGO_42"
    logo_path = fixtures_dir / "logo.png"
    logo_img = Image.new("RGB", (320, 100), color=(255, 255, 255))
    draw_logo = ImageDraw.Draw(logo_img)
    draw_logo.text((25, 28), "LOGO 42", fill=(0, 0, 0), font=_load_font(40))
    logo_img.save(logo_path, format="PNG")

    # 2. Create ocr_fixture.png with known text "SECRET CODE 987"
    ocr_path = fixtures_dir / "ocr_fixture.png"
    ocr_img = Image.new("RGB", (420, 110), color=(255, 255, 255))
    draw_ocr = ImageDraw.Draw(ocr_img)
    draw_ocr.text((25, 30), "SECRET CODE 987", fill=(0, 0, 0), font=_load_font(38))
    ocr_img.save(ocr_path, format="PNG")

    # 3. Create blank_gradient.png (no text, no alt -> triggers ocr_failed)
    blank_path = fixtures_dir / "blank.png"
    blank_img = Image.new("RGB", (120, 60), color=(120, 140, 160))
    blank_img.save(blank_path, format="PNG")

    # 4. index.html: headings, text blocks, 2 links, 2 images, noise script/style
    index_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fixture Index Page</title>
    <style>body { font-family: sans-serif; } .hidden-css { color: red; }</style>
    <script>var secretNoise = "SHOULD_NOT_APPEAR_IN_TEXT_BLOCKS";</script>
</head>
<body>
    <h1>Main Welcome Heading</h1>
    <p>First paragraph of clean body text for the reader test.</p>
    <h2>Secondary Section Heading</h2>
    <p>Second paragraph with useful details.</p>
    <img src="/logo.png" alt="logo" width="320" height="100" />
    <img src="/ocr_fixture.png" alt="banner" width="420" height="110" />
    <div class="nav">
        <a id="link-forms" href="/forms.html">Go to Forms</a>
        <a id="link-next" href="/next.html">Next Page</a>
    </div>
</body>
</html>"""
    (fixtures_dir / "index.html").write_text(index_html, encoding="utf-8")

    # 5. forms.html: inputs, select, checkbox, toggle button, submit form, dangerous button
    forms_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fixture Forms Page</title>
</head>
<body>
    <h1>Interactive Form</h1>
    <form id="search-form" action="/next.html" method="get">
        <label for="search-input">Search Query</label>
        <input id="search-input" name="q" type="text" value="" placeholder="Type query" />

        <label for="role-select">User Role</label>
        <select id="role-select" name="role">
            <option value="guest">Guest</option>
            <option value="admin">Admin</option>
            <option value="editor">Editor</option>
        </select>

        <label for="agree-check">Agree to Terms</label>
        <input id="agree-check" name="agree" type="checkbox" value="yes" />

        <button id="submit-btn" type="submit">Submit</button>
    </form>

    <button id="toggle-btn" type="button" onclick="this.textContent = (this.textContent === 'OFF' ? 'ON' : 'OFF'); document.getElementById('toggle-status').textContent = 'STATE_' + this.textContent;">OFF</button>
    <div id="toggle-status">STATE_OFF</div>

    <a id="nav-next" href="/next.html">Navigate Next</a>
    <button id="danger-btn" type="button">Delete Account</button>
</body>
</html>"""
    (fixtures_dir / "forms.html").write_text(forms_html, encoding="utf-8")

    # 6. next.html: destination page
    next_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Next Destination Page</title>
</head>
<body>
    <h1>Arrived at Next Page</h1>
    <p>Navigation succeeded.</p>
    <a id="back-home" href="/index.html">Back to Index</a>
</body>
</html>"""
    (fixtures_dir / "next.html").write_text(next_html, encoding="utf-8")

    # 7. login.html: sets cookie on submit and navigates to /dashboard
    login_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Login Page</title></head>
<body>
    <h1>Sign In</h1>
    <form id="login-form" action="/do_login" method="get">
        <label for="user-field">Username</label>
        <input id="user-field" name="username" type="text" value="" />
        <label for="pass-field">Password</label>
        <input id="pass-field" name="password" type="password" value="" />
        <button id="login-btn" type="submit">Login</button>
    </form>
</body>
</html>"""
    (fixtures_dir / "login.html").write_text(login_html, encoding="utf-8")

    return fixtures_dir


class _FixtureRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving files from fixtures/ plus dynamic test endpoints."""

    fixtures_root: Path = get_repo_root() / "fixtures"

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        rel = parsed.path.lstrip("/") or "index.html"
        return str((self.fixtures_root / rel).resolve())

    def log_message(self, format: str, *args) -> None:
        # Suppress console noise during tests
        pass

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/hang":
            time.sleep(3.0)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>Finally loaded</body></html>")
            return

        if parsed.path == "/do_login":
            params = parse_qs(parsed.query)
            user = params.get("username", ["user"])[0]
            self.send_response(302)
            self.send_header("Set-Cookie", f"session_user={user}; Path=/")
            self.send_header("Location", "/dashboard")
            self.end_headers()
            return

        if parsed.path == "/dashboard":
            cookie_hdr = self.headers.get("Cookie", "")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if "session_user=" in cookie_hdr:
                body = f"<html><head><title>Dashboard</title></head><body><h1>Welcome Authenticated User</h1><p id='cookie-val'>{cookie_hdr}</p></body></html>"
            else:
                body = "<html><head><title>Unauthorized</title></head><body><h1>Access Denied</h1></body></html>"
            self.wfile.write(body.encode("utf-8"))
            return

        super().do_GET()


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return ensure_fixtures_created()


@pytest.fixture(scope="session")
def test_server_url(fixtures_dir: Path) -> Generator[str, None, None]:
    """Start a local threaded HTTP server serving fixtures_dir."""
    _FixtureRequestHandler.fixtures_root = fixtures_dir
    server = _ThreadedTCPServer(("127.0.0.1", 0), _FixtureRequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def temp_config(tmp_path: Path) -> DriverConfig:
    """Provide a DriverConfig isolated to a temporary artifacts directory."""
    return DriverConfig(
        artifacts_dir=tmp_path / "artifacts",
        timeout_ms=5000,
        ocr_langs="eng",
        ocr_min_conf=50.0,
        headless=True,
    )
