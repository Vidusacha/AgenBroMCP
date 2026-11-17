"""DOM content reader and actionable element mapper (Phases 2 and 4)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from playwright.sync_api import Page


def compute_normalized_html_hash(html: str) -> str:
    """Compute a SHA-256 hash of normalized DOM content (excluding script/style noise)."""
    soup = BeautifulSoup(html, "html.parser")
    for noisy in soup(["script", "style", "noscript", "template"]):
        noisy.decompose()
    normalized = " ".join(soup.get_text(separator=" ").split())
    # Also include input values/checked states and form structure in hash
    states = []
    for el in soup.find_all(["input", "select", "textarea", "button", "a"]):
        states.append(
            f"{el.name}:{el.get('id','')}:{el.get('name','')}:{el.get('value','')}:{el.get('checked','')}:{el.get_text(strip=True)}"
        )
    payload = normalized + "||" + "|".join(states)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_headings(page: Page) -> List[Dict[str, Any]]:
    """Extract headings (h1-h6) in DOM order."""
    return page.evaluate(
        """() => {
            const nodes = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
            return nodes.map(el => ({
                tag: el.tagName.toLowerCase(),
                level: parseInt(el.tagName.substring(1), 10),
                text: (el.innerText || el.textContent || '').trim()
            })).filter(h => h.text.length > 0);
        }"""
    )


def read_text(page: Page) -> List[str]:
    """Extract clean text blocks from body without script/style noise."""
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    body = soup.body or soup
    blocks: List[str] = []
    for line in body.get_text(separator="\n").splitlines():
        cleaned = " ".join(line.split())
        if cleaned:
            blocks.append(cleaned)
    return blocks


def read_links(page: Page) -> List[Dict[str, str]]:
    """Extract all links (<a> with href) from the page."""
    return page.evaluate(
        """() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => ({
                href: a.href || a.getAttribute('href') || '',
                raw_href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || '').trim()
            }));
        }"""
    )


def read_images(page: Page) -> List[Dict[str, Any]]:
    """Extract inventory of all <img> elements on the page (URL, alt, role, natural size)."""
    return page.evaluate(
        """() => {
            const imgs = Array.from(document.querySelectorAll('img'));
            return imgs.map((img, idx) => {
                img.setAttribute('data-agb-img-idx', String(idx));
                const rect = img.getBoundingClientRect();
                const w = img.naturalWidth || Math.round(rect.width) || img.width || 0;
                const h = img.naturalHeight || Math.round(rect.height) || img.height || 0;
                return {
                    index: idx,
                    url: img.currentSrc || img.src || img.getAttribute('src') || '',
                    raw_src: img.getAttribute('src') || '',
                    alt: (img.getAttribute('alt') || '').trim(),
                    role: img.getAttribute('role') || 'img',
                    size: { width: w, height: h },
                    width: w,
                    height: h
                };
            });
        }"""
    )


def collect_actionables(page: Page) -> List[Dict[str, Any]]:
    """Collect a deduplicated, deterministic registry of interactive elements on the page."""
    return page.evaluate(
        """() => {
            const selectorQuery = 'input:not([type="hidden"]), select, textarea, button, a[href], [role="button"], [role="link"], [role="checkbox"]';
            const rawNodes = Array.from(document.querySelectorAll(selectorQuery));
            const seen = new Set();
            const results = [];

            function cssEscape(str) {
                if (window.CSS && window.CSS.escape) return window.CSS.escape(str);
                return str.replace(/([!"#$%&'()*+,.\\/:;<=>?@[\\\\\\]^`{|}~])/g, '\\\\$1');
            }

            function getCssPath(el) {
                const parts = [];
                let cur = el;
                while (cur && cur.nodeType === Node.ELEMENT_NODE && cur.tagName.toLowerCase() !== 'html') {
                    let tag = cur.tagName.toLowerCase();
                    if (cur.id) {
                        parts.unshift('#' + cssEscape(cur.id));
                        break;
                    }
                    let nth = 1;
                    let sib = cur.previousElementSibling;
                    while (sib) {
                        if (sib.tagName === cur.tagName) nth++;
                        sib = sib.previousElementSibling;
                    }
                    parts.unshift(`${tag}:nth-of-type(${nth})`);
                    cur = cur.parentElement;
                }
                return parts.join(' > ');
            }

            function findLabel(el) {
                const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                if (ariaLabel) return ariaLabel;

                const labelledBy = el.getAttribute('aria-labelledby');
                if (labelledBy) {
                    const refEl = document.getElementById(labelledBy);
                    if (refEl) {
                        const txt = (refEl.innerText || refEl.textContent || '').trim();
                        if (txt) return txt;
                    }
                }

                if (el.id) {
                    const explicitLabel = document.querySelector(`label[for="${cssEscape(el.id)}"]`);
                    if (explicitLabel) {
                        const txt = (explicitLabel.innerText || explicitLabel.textContent || '').trim();
                        if (txt) return txt;
                    }
                }

                const parentLabel = el.closest('label');
                if (parentLabel) {
                    const clone = parentLabel.cloneNode(true);
                    const inputs = clone.querySelectorAll('input, select, textarea, button');
                    inputs.forEach(n => n.remove());
                    const txt = (clone.innerText || clone.textContent || '').trim();
                    if (txt) return txt;
                }

                const placeholder = (el.getAttribute('placeholder') || '').trim();
                if (placeholder) return placeholder;

                const title = (el.getAttribute('title') || '').trim();
                if (title) return title;

                const inner = (el.innerText || el.textContent || el.value || '').trim();
                if (inner) return inner;

                return el.getAttribute('name') || el.id || '';
            }

            function buildPrioritySelector(el, tag, role, text) {
                const idAttr = (el.getAttribute('id') || '').trim();
                if (idAttr) {
                    return '#' + cssEscape(idAttr);
                }
                const nameAttr = (el.getAttribute('name') || '').trim();
                if (nameAttr) {
                    const sameName = document.querySelectorAll(`${tag}[name="${cssEscape(nameAttr)}"]`);
                    if (sameName.length === 1) {
                        return `${tag}[name="${nameAttr}"]`;
                    }
                    const valAttr = el.getAttribute('value');
                    if (valAttr) {
                        return `${tag}[name="${nameAttr}"][value="${valAttr}"]`;
                    }
                }
                const ariaAttr = (el.getAttribute('aria-label') || '').trim();
                if (ariaAttr) {
                    return `${tag}[aria-label="${ariaAttr}"]`;
                }
                if ((tag === 'button' || tag === 'a') && text) {
                    const sameText = Array.from(document.querySelectorAll(tag)).filter(
                        n => (n.innerText || n.textContent || '').trim() === text
                    );
                    if (sameText.length === 1) {
                        return `${tag}:has-text("${text.replace(/"/g, '\\\\"')}")`;
                    }
                }
                return getCssPath(el);
            }

            rawNodes.forEach((el) => {
                if (seen.has(el)) return;
                seen.add(el);

                const idx = results.length + 1;
                const actionId = `act_${idx}`;
                el.setAttribute('data-agb-id', actionId);

                const tag = el.tagName.toLowerCase();
                const inputType = (el.getAttribute('type') || '').toLowerCase();
                let role = el.getAttribute('role') || '';
                if (!role) {
                    if (tag === 'a') role = 'link';
                    else if (tag === 'button' || inputType === 'submit' || inputType === 'button') role = 'button';
                    else if (tag === 'select') role = 'combobox';
                    else if (inputType === 'checkbox') role = 'checkbox';
                    else if (inputType === 'radio') role = 'radio';
                    else role = 'textbox';
                }

                const text = (el.innerText || el.textContent || (inputType === 'submit' || inputType === 'button' ? el.value : '') || '').trim();
                const label = findLabel(el);
                const selector = buildPrioritySelector(el, tag, role, text);
                const href = tag === 'a' ? (el.href || el.getAttribute('href') || '') : null;
                const value = ('value' in el) ? (el.value || '') : '';
                const checked = ('checked' in el) ? Boolean(el.checked) : null;

                results.push({
                    id: actionId,
                    role: role,
                    tag: tag,
                    type: inputType || tag,
                    label: label,
                    text: text,
                    name: el.getAttribute('name') || '',
                    value: value,
                    checked: checked,
                    href: href,
                    selector: selector
                });
            });

            return results;
        }"""
    )


def read_page_Snapshot(page: Page) -> Dict[str, Any]:
    """Read structured DOM content (headings, text_blocks, links, images, actionables)."""
    headings = read_headings(page)
    text_blocks = read_text(page)
    links = read_links(page)
    images = read_images(page)
    actionables = collect_actionables(page)
    return {
        "headings": headings,
        "text_blocks": text_blocks,
        "text": "\n".join(text_blocks),
        "links": links,
        "images": images,
        "actionables": actionables,
    }
