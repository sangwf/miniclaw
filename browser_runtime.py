from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def load_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Install it into the current Python environment "
            "with `pip install -r requirements-browser.txt` and then run "
            "`python -m playwright install chromium`."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


class FixtureServer:
    def __init__(self, root: Path, port: int = 0) -> None:
        self.root = root
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "FixtureServer":
        handler = partial(_QuietHandler, directory=str(self.root))
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("fixture server is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"


@dataclass
class BrowserObservation:
    ok: bool
    step_index: int
    requested_action: dict[str, Any]
    normalized_action: dict[str, Any]
    pre_url: str | None
    post_url: str | None
    title: str | None
    visible_text: str
    interactive_elements: list[dict[str, str]]
    extracted: dict[str, Any] | None
    elapsed_ms: int
    screenshot_path: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrowserHarness:
    def __init__(
        self,
        run_dir: Path,
        *,
        headless: bool = True,
        timeout_ms: int = 10_000,
        viewport: tuple[int, int] = (1280, 900),
    ) -> None:
        self.run_dir = run_dir.resolve()
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.viewport = viewport
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._step_index = 0

    def __enter__(self) -> "BrowserHarness":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._page is not None:
            return
        sync_playwright, _ = load_playwright()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(viewport={"width": self.viewport[0], "height": self.viewport[1]})
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        self._context = None
        self._browser = None
        self._pw = None
        self._page = None

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("browser harness has not been started")
        return self._page

    @property
    def step_index(self) -> int:
        return self._step_index

    def navigate(self, url: str) -> BrowserObservation:
        self.start()
        return self.execute({"kind": "navigate", "url": url})

    def snapshot(self) -> BrowserObservation:
        self.start()
        return self.execute({"kind": "snapshot"})

    def act(self, action: str, target: str, value: str | None = None) -> BrowserObservation:
        self.start()
        payload: dict[str, Any] = {"kind": "act", "action": action, "target": target}
        if value is not None:
            payload["value"] = value
        return self.execute(payload)

    def extract(self, kind: str) -> BrowserObservation:
        self.start()
        return self.execute({"kind": "extract", "extract_kind": kind})

    def execute(self, step: dict[str, Any], *, base_url: str | None = None) -> BrowserObservation:
        self._step_index += 1
        return self.execute_step(self._step_index, step, base_url=base_url)

    def execute_step(
        self,
        step_index: int,
        step: dict[str, Any],
        *,
        base_url: str | None = None,
    ) -> BrowserObservation:
        self.start()
        _, PlaywrightTimeoutError = load_playwright()
        requested = dict(step)
        normalized = dict(step)
        if normalized.get("kind") == "navigate" and "path" in normalized:
            if not base_url:
                raise ValueError("base_url is required when navigate step uses a relative path")
            normalized["url"] = base_url + str(normalized.pop("path"))

        pre_url = self.page.url or None
        start = time.perf_counter()
        extracted: dict[str, Any] | None = None
        error_message: str | None = None
        ok = True

        try:
            kind = normalized["kind"]
            if kind == "navigate":
                self.page.goto(str(normalized["url"]), wait_until="domcontentloaded")
            elif kind == "snapshot":
                pass
            elif kind == "extract":
                extracted = self._extract(str(normalized.get("extract_kind") or "text"))
            elif kind == "act":
                self._apply_action(normalized)
            else:
                raise ValueError(f"unsupported step kind: {kind}")
        except PlaywrightTimeoutError as exc:
            ok = False
            error_message = f"timeout: {exc}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            error_message = str(exc)

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        screenshot_path = self.run_dir / "steps" / f"{step_index:03d}.png"
        screenshot_rel: str | None = None
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            screenshot_rel = str(screenshot_path)
        except Exception:  # noqa: BLE001
            screenshot_rel = None

        title = None
        visible_text = ""
        interactive_elements: list[dict[str, str]] = []
        try:
            title = self.page.title()
        except Exception:  # noqa: BLE001
            title = None
        try:
            visible_text = self.page.locator("body").inner_text()[:4000]
        except Exception:  # noqa: BLE001
            visible_text = ""
        try:
            interactive_elements = self._collect_interactive_elements()
        except Exception:  # noqa: BLE001
            interactive_elements = []

        observation = BrowserObservation(
            ok=ok,
            step_index=step_index,
            requested_action=requested,
            normalized_action=normalized,
            pre_url=pre_url,
            post_url=self.page.url or None,
            title=title,
            visible_text=visible_text,
            interactive_elements=interactive_elements,
            extracted=extracted,
            elapsed_ms=elapsed_ms,
            screenshot_path=screenshot_rel,
            error=error_message,
        )
        step_json = self.run_dir / "steps" / f"{step_index:03d}.json"
        step_json.parent.mkdir(parents=True, exist_ok=True)
        step_json.write_text(json.dumps(observation.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return observation

    def _apply_action(self, normalized: dict[str, Any]) -> None:
        action = str(normalized.get("action") or "")
        target = str(normalized.get("target") or "")
        value = normalized.get("value")
        if action == "click":
            self.page.locator(target).click()
            return
        if action == "type":
            self.page.locator(target).fill(str(value or ""))
            return
        if action == "press":
            self.page.locator(target).press(str(value or "Enter"))
            return
        if action == "wait":
            locator = self.page.locator(target)
            locator.wait_for(state="visible")
            if value:
                expected = str(value)
                deadline = time.time() + (self.timeout_ms / 1000.0)
                while time.time() < deadline:
                    text = locator.inner_text()
                    if expected in text:
                        return
                    time.sleep(0.1)
                raise TimeoutError(f"expected text {expected!r} not found in {target}")
            return
        raise ValueError(f"unsupported browser action: {action}")

    def _extract(self, kind: str) -> dict[str, Any]:
        if kind == "text":
            return {"kind": "text", "value": self.page.locator("body").inner_text()[:4000]}
        if kind == "list":
            items = self.page.locator("[data-testid='result-item'], [data-testid='results'] li, li").all_inner_texts()
            return {"kind": "list", "value": [item.strip() for item in items if item.strip()][:20]}
        raise ValueError(f"unsupported extract kind: {kind}")

    def _collect_interactive_elements(self) -> list[dict[str, str]]:
        locator = self.page.locator("a, button, input, textarea, select")
        count = min(locator.count(), 20)
        elements: list[dict[str, str]] = []
        for index in range(count):
            item = locator.nth(index)
            tag = item.evaluate("el => el.tagName.toLowerCase()")
            data_testid = item.get_attribute("data-testid") or ""
            item_id = item.get_attribute("id") or ""
            aria_label = item.get_attribute("aria-label") or ""
            placeholder = item.get_attribute("placeholder") or ""
            text = ""
            if tag in {"input", "textarea", "select"}:
                text = item.input_value() or ""
            else:
                try:
                    text = item.inner_text(timeout=500).strip()
                except Exception:  # noqa: BLE001
                    text = ""
            selector_hint = (
                f"[data-testid='{data_testid}']"
                if data_testid
                else (f"#{item_id}" if item_id else tag)
            )
            label = aria_label or placeholder or data_testid or item_id or text
            elements.append(
                {
                    "tag": tag,
                    "text": text,
                    "label": label,
                    "selector_hint": selector_hint,
                }
            )
        return elements
