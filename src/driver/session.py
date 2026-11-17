"""Core BrowserDriver managing Playwright sessions, DOM actions, OCR, and artifacts."""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from .config import DriverConfig
from .ocr import run_ocr_on_file
from .reader import (
    collect_actionables,
    compute_normalized_html_hash,
    read_headings,
    read_images,
    read_links,
    read_text,
)
from .safety import ActionLimitError, SafetyError, check_destructive_action, check_url_allowed


def _slugify(value: str) -> str:
    """Create a filesystem-safe slug from a URL or page name."""
    parsed = urlparse(value)
    raw = (parsed.netloc + "_" + parsed.path).strip("_/") if parsed.netloc else value
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    return (slug[:40] or "page").lower()


class BrowserDriver:
    """Stateful browser driver with artifact snapshotting, OCR, and safety guards."""

    def __init__(
        self,
        session_id: str = "default",
        config: Optional[DriverConfig] = None,
    ) -> None:
        self.session_id = session_id
        self.config = config or DriverConfig.from_file()
        self.session_dir: Path = self.config.artifacts_dir / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.storage_state_path: Path = self.session_dir / "storage_state.json"
        self.session_actions_log: Path = self.session_dir / "actions.log"
        self.session_state_log: Path = self.session_dir / "session.log"

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self.page_counter: int = 0
        self.action_count: int = 0
        self.screenshot_count: int = 0
        self.download_count: int = 0
        self.current_page_dir: Optional[Path] = None
        self.current_page_id: Optional[str] = None
        self.last_html_hash: str = ""
        self.last_html_content: str = ""

    def start(self) -> None:
        """Start Playwright Chromium and initialize BrowserContext (loading storage_state if present)."""
        if self._page is not None:
            return
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.config.headless)

        context_kwargs: Dict[str, Any] = {
            "user_agent": self.config.user_agent,
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
        }
        if self.storage_state_path.is_file():
            context_kwargs["storage_state"] = str(self.storage_state_path)

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.config.timeout_ms)
        self._page = self._context.new_page()

    @property
    def page(self) -> Page:
        """Return active Playwright page, starting session if needed."""
        if self._page is None:
            self.start()
        assert self._page is not None
        return self._page

    def save_state(self) -> Optional[Path]:
        """Persist cookies and localStorage to session storage_state.json."""
        if self._context is not None:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self._context.storage_state(path=str(self.storage_state_path))
            return self.storage_state_path
        return None

    def close(self) -> None:
        """Save session state and close Playwright resources."""
        try:
            self.save_state()
        except Exception:
            pass
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None
        self._page = None

    def __enter__(self) -> "BrowserDriver":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _check_and_increment_action(self) -> None:
        if self.action_count >= self.config.max_actions:
            raise ActionLimitError(
                f"Exceeded maximum actions limit ({self.config.max_actions}) for session '{self.session_id}'."
            )
        self.action_count += 1

    def _resolve_locator(self, selector: str):
        """Resolve an actionable ID (`act_1`) or standard CSS/Playwright selector to a first Locator."""
        if re.match(r"^act_\d+$", selector):
            return self.page.locator(f'[data-agb-id="{selector}"]').first
        return self.page.locator(selector).first

    def _append_action_log(self, record: Dict[str, Any]) -> None:
        """Write action record to both session actions.log and current page actions.log."""
        line = json.dumps(record, ensure_ascii=False) + "\n"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with self.session_actions_log.open("a", encoding="utf-8") as f:
            f.write(line)
        if self.current_page_dir is not None:
            page_log = self.current_page_dir / "actions.log"
            with page_log.open("a", encoding="utf-8") as f:
                f.write(line)

    def _process_page_images(self, page_dir: Path, run_ocr: bool = True) -> List[Dict[str, Any]]:
        """Inventory all <img> elements, capture/download each, and run OCR."""
        raw_inventory = read_images(self.page)
        images_dir = page_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        processed: List[Dict[str, Any]] = []
        for item in raw_inventory:
            idx = item["index"]
            url = item.get("url", "")
            alt = item.get("alt", "")
            img_file = images_dir / f"img_{idx}.png"
            saved_ok = False

            if self.download_count < self.config.max_downloads:
                # 1. Try data: URI decoding first if applicable
                if url.startswith("data:image/") and ";base64," in url:
                    try:
                        b64_data = url.split(";base64,", 1)[1]
                        img_file.write_bytes(base64.b64decode(b64_data))
                        saved_ok = True
                    except Exception:
                        saved_ok = False

                # 2. Try direct HTTP fetch via browser context request if http/https
                if not saved_ok and url.startswith(("http://", "https://")) and self._context is not None:
                    try:
                        resp = self._context.request.get(url, timeout=self.config.timeout_ms)
                        if resp.ok:
                            img_file.write_bytes(resp.body())
                            saved_ok = True
                    except Exception:
                        saved_ok = False

                # 3. Fallback to Playwright element screenshot (handles file://, SVG, canvas, relative URLs)
                if not saved_ok:
                    try:
                        loc = self.page.locator(f'img[data-agb-img-idx="{idx}"]').first
                        loc.screenshot(path=str(img_file), timeout=3000)
                        saved_ok = True
                    except Exception:
                        saved_ok = False

                if saved_ok:
                    self.download_count += 1

            ocr_text = "ocr_failed"
            conf = 0.0
            status = "ocr_failed"
            actual_size = item.get("size", {"width": 0, "height": 0})

            if saved_ok and img_file.is_file():
                try:
                    with Image.open(img_file) as pil_img:
                        actual_size = {"width": pil_img.width, "height": pil_img.height}
                    if run_ocr:
                        ocr_res = run_ocr_on_file(
                            img_file,
                            lang=self.config.ocr_langs,
                            min_conf=self.config.ocr_min_conf,
                            alt_text=alt,
                            use_preprocess=True,
                        )
                        ocr_text = ocr_res.text
                        conf = ocr_res.conf
                        status = ocr_res.status
                except Exception:
                    if alt:
                        ocr_text = alt
                        status = "fallback_alt"
                    else:
                        ocr_text = "ocr_failed"
                        status = "ocr_failed"
            else:
                if alt:
                    ocr_text = alt
                    status = "fallback_alt"

            processed.append(
                {
                    "index": idx,
                    "url": url,
                    "alt": alt,
                    "role": item.get("role", "img"),
                    "size": actual_size,
                    "file": str(img_file) if saved_ok else None,
                    "ocr_text": ocr_text,
                    "conf": conf,
                    "status": status,
                }
            )
        return processed

    def capture_snapshot(
        self,
        label: Optional[str] = None,
        run_ocr: bool = True,
    ) -> Dict[str, Any]:
        """Create a full page snapshot directory with page.html, page.png, manifest.json, and diff."""
        if self.screenshot_count >= self.config.max_screenshots:
            raise ActionLimitError(f"Exceeded max_screenshots ({self.config.max_screenshots}).")

        self.page_counter += 1
        url = self.page.url
        slug = _slugify(label or url)
        page_id = f"page_{self.page_counter:03d}_{slug}"
        page_dir = self.session_dir / page_id
        page_dir.mkdir(parents=True, exist_ok=True)

        self.current_page_dir = page_dir
        self.current_page_id = page_id

        # Ensure actions.log exists inside page_dir as well
        page_actions_log = page_dir / "actions.log"
        if not page_actions_log.exists():
            if self.session_actions_log.is_file():
                page_actions_log.write_text(
                    self.session_actions_log.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            else:
                page_actions_log.write_text("", encoding="utf-8")

        try:
            html_content = self.page.content()
        except PlaywrightError:
            html_content = "<html><body><!-- Page navigating or timed out --></body></html>"
        html_path = page_dir / "page.html"
        html_path.write_text(html_content, encoding="utf-8")

        png_path = page_dir / "page.png"
        try:
            png_bytes = self.page.screenshot(path=str(png_path), type="png", timeout=2000)
        except PlaywrightError:
            fallback_img = Image.new("RGB", (400, 300), color=(255, 255, 255))
            fallback_img.save(png_path, format="PNG")
            png_bytes = png_path.read_bytes()
        self.screenshot_count += 1

        new_html_hash = compute_normalized_html_hash(html_content)
        screenshot_hash = hashlib.sha256(png_bytes).hexdigest()

        # Compute HTML diff against previous snapshot in this session
        diff_path = page_dir / "page.diff"
        diff_lines = list(
            difflib.unified_diff(
                self.last_html_content.splitlines(),
                html_content.splitlines(),
                fromfile="before.html",
                tofile="after.html",
                lineterm="",
            )
        )
        diff_text = "\n".join(diff_lines)
        diff_path.write_text(diff_text, encoding="utf-8")

        prev_hash = self.last_html_hash
        html_changed = (prev_hash != new_html_hash) if prev_hash else True
        self.last_html_hash = new_html_hash
        self.last_html_content = html_content

        # Extract structured DOM and run OCR on page images
        try:
            headings = read_headings(self.page)
            text_blocks = read_text(self.page)
            links = read_links(self.page)
            actionables = collect_actionables(self.page)
            images = (
                self._process_page_images(page_dir, run_ocr=run_ocr)
                if label not in ("timeout", "timeout_cleanup")
                else []
            )
            page_title = self.page.title()
        except PlaywrightError:
            headings, text_blocks, links, actionables, images = [], [], [], [], []
            page_title = ""

        ts = datetime.now(timezone.utc).isoformat()
        manifest: Dict[str, Any] = {
            "session": self.session_id,
            "page_id": page_id,
            "url": url,
            "title": page_title,
            "screenshot": str(png_path),
            "html_path": str(html_path),
            "diff_path": str(diff_path),
            "actions_log": str(page_actions_log),
            "ts": ts,
            "html_hash_before": prev_hash or None,
            "html_hash": new_html_hash,
            "html_changed": html_changed,
            "screenshot_hash": screenshot_hash,
            "headings": headings,
            "text_blocks": text_blocks,
            "links": links,
            "images": images,
            "actionables": actionables,
        }

        manifest_path = page_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Record state transition in session.log
        state_entry = {
            "ts": ts,
            "session": self.session_id,
            "page_id": page_id,
            "url": url,
            "html_hash_before": prev_hash or None,
            "html_hash": new_html_hash,
            "html_changed": html_changed,
            "screenshot_hash": screenshot_hash,
            "diff_lines_count": len(diff_lines),
        }
        with self.session_state_log.open("a", encoding="utf-8") as sf:
            sf.write(json.dumps(state_entry, ensure_ascii=False) + "\n")

        self.save_state()
        return manifest

    def open_page(self, url: str, run_ocr: bool = True) -> Dict[str, Any]:
        """Navigate to URL, create artifacts directory, and return the page manifest."""
        check_url_allowed(url, self.config.allowed_domains)
        self._check_and_increment_action()

        url_before = self.page.url if self._page else "about:blank"
        hash_before = self.last_html_hash

        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
        except PlaywrightTimeoutError as exc:
            # Capture emergency timeout artifact so process never hangs silently
            manifest = self.capture_snapshot(label="timeout", run_ocr=False)
            raise TimeoutError(f"Navigation timed out for URL '{url}': {exc}") from exc

        manifest = self.capture_snapshot(run_ocr=run_ocr)
        self._append_action_log(
            {
                "action": "open",
                "selector": None,
                "value": url,
                "before": url_before,
                "after": self.page.url,
                "url_before": url_before,
                "url_after": self.page.url,
                "html_hash_before": hash_before or None,
                "html_hash_after": manifest["html_hash"],
                "page_id": manifest["page_id"],
                "session": self.session_id,
                "ts": manifest["ts"],
            }
        )
        return manifest

    def goto(self, url: str, run_ocr: bool = True) -> Dict[str, Any]:
        """Alias for open_page."""
        return self.open_page(url, run_ocr=run_ocr)

    def read(self) -> Dict[str, Any]:
        """Read current page DOM structure, links, headings, text blocks, images, and actionables."""
        headings = read_headings(self.page)
        text_blocks = read_text(self.page)
        links = read_links(self.page)
        actionables = collect_actionables(self.page)
        images = (
            self._process_page_images(self.current_page_dir, run_ocr=True)
            if self.current_page_dir is not None
            else read_images(self.page)
        )
        return {
            "url": self.page.url,
            "title": self.page.title(),
            "headings": headings,
            "text_blocks": text_blocks,
            "text": "\n".join(text_blocks),
            "links": links,
            "images": images,
            "actionables": actionables,
        }

    def read_text(self) -> List[str]:
        return read_text(self.page)

    def read_links(self) -> List[Dict[str, str]]:
        return read_links(self.page)

    def read_images(self) -> List[Dict[str, Any]]:
        return read_images(self.page)

    def read_headings(self) -> List[Dict[str, Any]]:
        return read_headings(self.page)

    def collect_actionables(self) -> List[Dict[str, Any]]:
        return collect_actionables(self.page)

    def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill an input/textarea field, verify post-fill DOM value, and log before/after."""
        self._check_and_increment_action()
        loc = self._resolve_locator(selector)
        before_val = loc.input_value(timeout=self.config.timeout_ms)
        loc.fill(str(value), timeout=self.config.timeout_ms)
        after_val = loc.input_value(timeout=self.config.timeout_ms)

        record = {
            "action": "fill",
            "selector": selector,
            "value": str(value),
            "before": before_val,
            "after": after_val,
            "url_before": self.page.url,
            "url_after": self.page.url,
            "page_id": self.current_page_id,
            "session": self.session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._append_action_log(record)
        self.save_state()
        return record

    def select(self, selector: str, option: str) -> Dict[str, Any]:
        """Select an option in a <select> element and log before/after value."""
        self._check_and_increment_action()
        loc = self._resolve_locator(selector)
        before_val = loc.input_value(timeout=self.config.timeout_ms)
        try:
            loc.select_option(value=option, timeout=self.config.timeout_ms)
        except PlaywrightError:
            loc.select_option(label=option, timeout=self.config.timeout_ms)
        after_val = loc.input_value(timeout=self.config.timeout_ms)

        record = {
            "action": "select",
            "selector": selector,
            "value": option,
            "before": before_val,
            "after": after_val,
            "url_before": self.page.url,
            "url_after": self.page.url,
            "page_id": self.current_page_id,
            "session": self.session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._append_action_log(record)
        self.save_state()
        return record

    def check(self, selector: str, checked: bool = True) -> Dict[str, Any]:
        """Check or uncheck a checkbox/radio input and log before/after boolean state."""
        self._check_and_increment_action()
        loc = self._resolve_locator(selector)
        before_state = loc.is_checked(timeout=self.config.timeout_ms)
        if checked:
            loc.check(timeout=self.config.timeout_ms)
        else:
            loc.uncheck(timeout=self.config.timeout_ms)
        after_state = loc.is_checked(timeout=self.config.timeout_ms)

        record = {
            "action": "check" if checked else "uncheck",
            "selector": selector,
            "value": checked,
            "before": before_state,
            "after": after_state,
            "url_before": self.page.url,
            "url_after": self.page.url,
            "page_id": self.current_page_id,
            "session": self.session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._append_action_log(record)
        self.save_state()
        return record

    def uncheck(self, selector: str) -> Dict[str, Any]:
        """Uncheck a checkbox."""
        return self.check(selector, checked=False)

    def click(
        self,
        selector: str,
        danger: bool = False,
        confirm: bool = False,
        run_ocr: bool = False,
    ) -> Dict[str, Any]:
        """Click an element/link, wait for navigation/DOM settle, and record transition snapshot."""
        self._check_and_increment_action()
        loc = self._resolve_locator(selector)

        el_text = ""
        try:
            el_text = (loc.inner_text(timeout=2000) or "").strip()
        except Exception:
            pass

        check_destructive_action(
            danger_flag=danger,
            confirm_flag=confirm,
            element_text=el_text,
            selector=selector,
        )

        url_before = self.page.url
        hash_before = self.last_html_hash or compute_normalized_html_hash(self.page.content())

        loc.click(timeout=self.config.timeout_ms)
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PlaywrightTimeoutError:
            pass

        check_url_allowed(self.page.url, self.config.allowed_domains)
        manifest = self.capture_snapshot(run_ocr=run_ocr)
        url_after = self.page.url
        hash_after = manifest["html_hash"]

        record = {
            "action": "click",
            "selector": selector,
            "value": el_text or None,
            "before": url_before,
            "after": url_after,
            "url_before": url_before,
            "url_after": url_after,
            "html_hash_before": hash_before,
            "html_hash_after": hash_after,
            "html_changed": hash_before != hash_after,
            "page_id": manifest["page_id"],
            "session": self.session_id,
            "ts": manifest["ts"],
            "manifest": manifest,
        }
        self._append_action_log({k: v for k, v in record.items() if k != "manifest"})
        return record

    def press(
        self,
        key: str,
        selector: Optional[str] = None,
        run_ocr: bool = False,
    ) -> Dict[str, Any]:
        """Press a key (e.g. 'Enter') on a selector or page, and capture post-action snapshot."""
        self._check_and_increment_action()
        url_before = self.page.url
        hash_before = self.last_html_hash or compute_normalized_html_hash(self.page.content())

        if selector:
            loc = self._resolve_locator(selector)
            loc.press(key, timeout=self.config.timeout_ms)
        else:
            self.page.keyboard.press(key)

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PlaywrightTimeoutError:
            pass

        manifest = self.capture_snapshot(run_ocr=run_ocr)
        url_after = self.page.url
        hash_after = manifest["html_hash"]

        record = {
            "action": "press",
            "selector": selector,
            "value": key,
            "before": url_before,
            "after": url_after,
            "url_before": url_before,
            "url_after": url_after,
            "html_hash_before": hash_before,
            "html_hash_after": hash_after,
            "html_changed": hash_before != hash_after,
            "page_id": manifest["page_id"],
            "session": self.session_id,
            "ts": manifest["ts"],
            "manifest": manifest,
        }
        self._append_action_log({k: v for k, v in record.items() if k != "manifest"})
        return record
