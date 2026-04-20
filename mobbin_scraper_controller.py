"""
Mobbin Scraper Browser Controller
Launches Chromium with the Mobbin Scraper extension, streams screenshots,
and forwards commands via a DOM event bridge.
"""

import asyncio
import base64
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright, Page

# Paths
EXTENSION_PATH = "/Users/mafruhurfaruqi/Desktop/Claude/mobbin-scraper"
DOWNLOAD_BASE_PATH = "/Users/mafruhurfaruqi"
USER_DATA_DIR = "/tmp/mobbin-chrome-profile"


class MobbinScraperController:
    """Headful Chromium orchestrator for the Mobbin Scraper extension."""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = threading.Event()

        # Thread-safe communication queues
        self.frame_queue: queue.Queue = queue.Queue(maxsize=5)
        self.command_queue: queue.Queue = queue.Queue()
        self.status: Dict[str, Any] = {
            "browser_running": False,
            "page_url": "",
            "scraper_running": False,
            "paused": False,
            "done_flows": 0,
            "total_flows": 0,
            "total_screens": 0,
            "status_msg": "Idle",
            "app_name": "",
            "category": "",
            "elapsed_ms": 0,
            "logs": [],
        }
        self._status_lock = threading.Lock()

        # Playwright handles (owned by the background thread)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Optional[Page] = None

    # ── Public API (called from Flask, synchronous) ───────────────────────────

    def start(self, url: str, app_name: str = "", category: str = "") -> None:
        """Launch the browser and navigate to the given Mobbin URL."""
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Browser already running. Stop it first.")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(url, app_name, category),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the browser to shut down."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        self._clear_queues()
        with self._status_lock:
            self.status = {
                "browser_running": False,
                "page_url": "",
                "scraper_running": False,
                "paused": False,
                "done_flows": 0,
                "total_flows": 0,
                "total_screens": 0,
                "status_msg": "Stopped",
                "app_name": "",
                "category": "",
                "elapsed_ms": 0,
                "logs": [],
            }

    def send_command(self, action: str, **kwargs) -> None:
        """Enqueue a command to be dispatched to the extension."""
        self.command_queue.put({"action": action, **kwargs})

    def get_frame(self) -> Optional[str]:
        """Return the latest JPEG frame as a base64 string (non-blocking)."""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None

    def get_status(self) -> Dict[str, Any]:
        """Return a snapshot of the current status."""
        with self._status_lock:
            return dict(self.status)

    # ── Background thread ─────────────────────────────────────────────────────

    def _run_loop(self, url: str, app_name: str, category: str) -> None:
        """Entry point for the background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run(url, app_name, category))
        except Exception as exc:
            with self._status_lock:
                self.status["status_msg"] = f"Browser error: {exc}"
        finally:
            with self._status_lock:
                self.status["browser_running"] = False

    async def _async_run(self, url: str, app_name: str, category: str) -> None:
        """Main async routine: launch browser, navigate, poll."""
        async with async_playwright() as pw:
            self._playwright = pw
            self._context = await self._launch_browser(pw)
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

            with self._status_lock:
                self.status["browser_running"] = True
                self.status["status_msg"] = "Navigating…"

            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait a moment for Mobbin's SPA to hydrate and the extension to inject
            await asyncio.sleep(3)

            with self._status_lock:
                self.status["page_url"] = self._page.url
                self.status["status_msg"] = "Ready — waiting for start command"

            # Start concurrent tasks
            await asyncio.gather(
                self._screenshot_loop(),
                self._status_loop(),
                self._command_loop(app_name, category),
            )

    async def _launch_browser(self, pw):
        """Launch Chromium with the Mobbin Scraper extension loaded."""
        # Ensure profile directory exists with correct download preference
        self._setup_chrome_profile()

        # Extensions require a headful (non-headless) browser.
        # On macOS this spawns a real window; we keep it minimised by
        # positioning it off-screen in a later iteration if needed.
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[
                f"--load-extension={EXTENSION_PATH}",
                f"--disable-extensions-except={EXTENSION_PATH}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1280,800",
                "--window-position=0,0",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateWindowOcclusion",
            ],
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
        )
        return context

    def _setup_chrome_profile(self) -> None:
        """Write Chrome Preferences so downloads land under DOWNLOAD_BASE_PATH."""
        default_dir = Path(USER_DATA_DIR) / "Default"
        default_dir.mkdir(parents=True, exist_ok=True)
        prefs_path = default_dir / "Preferences"

        prefs = {
            "download": {
                "default_directory": DOWNLOAD_BASE_PATH,
                "prompt_for_download": False,
            },
            "profile": {
                "default_content_setting_values": {
                    "automatic_downloads": 1,
                }
            },
        }

        # If a prefs file already exists, merge rather than overwrite
        if prefs_path.exists():
            try:
                existing = json.loads(prefs_path.read_text())
                existing.setdefault("download", {}).update(prefs["download"])
                existing.setdefault("profile", {}).update(prefs["profile"])
                prefs = existing
            except Exception:
                pass

        prefs_path.write_text(json.dumps(prefs))

    # ── Concurrent loops ──────────────────────────────────────────────────────

    async def _screenshot_loop(self) -> None:
        """Capture the page repeatedly and enqueue JPEG frames."""
        while not self._stop_event.is_set():
            try:
                if self._page and not self._page.is_closed():
                    screenshot = await self._page.screenshot(
                        type="jpeg",
                        quality=75,
                        full_page=False,
                    )
                    b64 = base64.b64encode(screenshot).decode("ascii")
                    # Drop oldest frame if queue is full
                    try:
                        self.frame_queue.put_nowait(b64)
                    except queue.Full:
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self.frame_queue.put_nowait(b64)
            except Exception:
                pass
            await asyncio.sleep(0.2)  # 5 FPS

    async def _status_loop(self) -> None:
        """Poll the extension for status every second."""
        while not self._stop_event.is_set():
            try:
                if self._page and not self._page.is_closed():
                    state = await self._page.evaluate(
                        """() => {
                            return new Promise((resolve) => {
                                const handler = (e) => {
                                    document.removeEventListener('mobbin-scraper-status-response', handler);
                                    resolve(e.detail);
                                };
                                document.addEventListener('mobbin-scraper-status-response', handler);
                                document.dispatchEvent(
                                    new CustomEvent('mobbin-scraper-command', { detail: { action: 'STATUS' } })
                                );
                                // Safety timeout in case extension isn't loaded
                                setTimeout(() => resolve(null), 2000);
                            });
                        }"""
                    )
                    if state:
                        with self._status_lock:
                            self.status.update({
                                "scraper_running": state.get("running", False),
                                "paused": state.get("paused", False),
                                "done_flows": state.get("doneFlows", 0),
                                "total_flows": state.get("totalFlows", 0),
                                "total_screens": state.get("totalScreens", 0),
                                "status_msg": state.get("statusMsg", ""),
                                "app_name": state.get("appName", ""),
                                "elapsed_ms": state.get("elapsedMs", 0),
                                "logs": state.get("newLogs", []),
                            })
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _command_loop(self, initial_app_name: str, initial_category: str) -> None:
        """Read commands from the queue and dispatch them to the extension."""
        while not self._stop_event.is_set():
            try:
                cmd = self.command_queue.get(timeout=0.2)
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue

            try:
                if cmd.get("action") == "START" and self._page and not self._page.is_closed():
                    app = cmd.get("appName", initial_app_name or "Unknown")
                    cat = cmd.get("category", initial_category or "")
                    await self._page.evaluate(
                        """(msg) => {
                            document.dispatchEvent(
                                new CustomEvent('mobbin-scraper-command', { detail: msg })
                            );
                        }""",
                        {"action": "START", "appName": app, "category": cat},
                    )
                elif cmd.get("action") in ("PAUSE", "RESUME", "STOP"):
                    await self._page.evaluate(
                        """(msg) => {
                            document.dispatchEvent(
                                new CustomEvent('mobbin-scraper-command', { detail: msg })
                            );
                        }""",
                        {"action": cmd["action"]},
                    )
                elif cmd.get("action") == "SCAN_CATEGORY":
                    await self._page.evaluate(
                        """(msg) => {
                            document.dispatchEvent(
                                new CustomEvent('mobbin-scraper-command', { detail: msg })
                            );
                        }""",
                        {"action": "SCAN_CATEGORY"},
                    )
                elif cmd.get("action") == "START_CATEGORY_MODE":
                    await self._page.evaluate(
                        """(msg) => {
                            document.dispatchEvent(
                                new CustomEvent('mobbin-scraper-command', { detail: msg })
                            );
                        }""",
                        {"action": "START_CATEGORY_MODE"},
                    )
            except Exception as exc:
                with self._status_lock:
                    self.status["status_msg"] = f"Command error: {exc}"

    def _clear_queues(self) -> None:
        for q in (self.frame_queue, self.command_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break


# Singleton controller instance (one browser session at a time)
_scraper_controller: Optional[MobbinScraperController] = None


def get_controller() -> MobbinScraperController:
    global _scraper_controller
    if _scraper_controller is None:
        _scraper_controller = MobbinScraperController()
    return _scraper_controller
