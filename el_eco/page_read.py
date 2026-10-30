"""Open a public GitHub page in a Browserbase browser and bring its words home.

Stagehand's extract step wants a separate model key. This path uses the
Browserbase session API and Playwright over the remote browser, then hands
the words to the local Gemma séance. Digits are removed so the eulogy
cannot launder a number off the page.
"""

from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger("el_eco")

API = "https://api.browserbase.com/v1"


def browserbase_configured() -> bool:
    return bool(os.environ.get("BROWSERBASE_API_KEY", "").strip())


def without_digits(text: str, limit: int = 900) -> str:
    cleaned = re.sub(r"\d+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]


def read_public_page(owner: str, repo: str) -> str:
    key = os.environ.get("BROWSERBASE_API_KEY", "").strip()
    if not key:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        return ""
    session_id = ""
    headers = {"X-BB-API-Key": key}
    try:
        created = _create_session(headers)
        session_id = str(created.get("id") or "")
        connect_url = created.get("connectUrl") or created.get("connect_url") or ""
        if not session_id or not connect_url:
            logger.info("browserbase session did not return a connect url")
            return ""
        raw = _read_over_cdp(connect_url, f"https://github.com/{owner}/{repo}")
        return without_digits(raw)
    except Exception as exc:
        logger.info("browserbase page read failed: %s", exc.__class__.__name__)
        return ""
    finally:
        if session_id:
            try:
                httpx.post(
                    f"{API}/sessions/{session_id}",
                    headers=headers,
                    json={"status": "REQUEST_RELEASE"},
                    timeout=20.0,
                )
            except httpx.HTTPError:
                logger.info("browserbase session release failed")


def _create_session(headers: dict[str, str]) -> dict:
    project = os.environ.get("BROWSERBASE_PROJECT_ID", "").strip()
    body: dict[str, str] = {"projectId": project} if project else {}
    response = httpx.post(f"{API}/sessions", headers=headers, json=body, timeout=30.0)
    if response.status_code == 400 and not project:
        listed = httpx.get(f"{API}/projects", headers=headers, timeout=20.0)
        if listed.status_code == 200:
            payload = listed.json()
            items = payload if isinstance(payload, list) else payload.get("projects") or payload.get("data") or []
            if items and isinstance(items, list) and items[0].get("id"):
                response = httpx.post(
                    f"{API}/sessions",
                    headers=headers,
                    json={"projectId": items[0]["id"]},
                    timeout=30.0,
                )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _read_over_cdp(connect_url: str, url: str) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(connect_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        parts: list[str] = []
        title = page.title()
        if title:
            parts.append(title)
        description = page.locator("meta[property='og:description']").get_attribute("content") or ""
        if description and description not in title:
            parts.append(description)
        browser.close()
        return "\n".join(parts)
