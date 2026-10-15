"""V8 coverage of the page scripts (gui/web/*.js), read from QtWebEngine.

Inert unless JS_COVERAGE=1 (scripts/coverage_check.py sets it). Spec:
docs/superpowers/specs/2026-10-15-coverage-and-snapshot-fixes-design.md section 6.

QtWebEngine serves Chrome DevTools on QTWEBENGINE_REMOTE_DEBUGGING. The
Collector auto-attaches to every page before its scripts run, starts precise
coverage, and after each test body takes what ran and ORs it into one map per
file. The DevTools endpoint is served on the Qt main thread, so nothing here
may block it: the one HTTP read runs on a thread, and the socket traffic is
QWebSocket inside the Qt event loop.
"""

import json
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ENABLED = os.environ.get("JS_COVERAGE") == "1"
WEB_DIR = (Path(__file__).resolve().parent.parent / "gui" / "web").resolve()
TAKE_TIMEOUT_S = 5.0


def enable_remote_debugging() -> None:
    """Give QtWebEngine a free DevTools port. Must run before QtWebEngine starts."""
    if not ENABLED or os.environ.get("QTWEBENGINE_REMOTE_DEBUGGING"):
        return
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{port}"


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def executed_units(length: int, functions: list[dict]) -> list[bool]:
    """Which UTF-16 units of a script ran, from one take's `functions`.

    Ranges nest, and a nested range is more specific than its parent: paint
    outer ranges first (start ascending, longest first), inner ones over them.
    """
    counts = [0] * length
    ranges = sorted(
        (r for f in functions for r in f["ranges"]),
        key=lambda r: (r["startOffset"], -r["endOffset"]),
    )
    for r in ranges:
        start, end = max(r["startOffset"], 0), min(r["endOffset"], length)
        if end > start:
            counts[start:end] = [r["count"]] * (end - start)
    return [count > 0 for count in counts]


def line_report(source: str, executed: list[bool]) -> tuple[int, list[int]]:
    """(executable lines, missed line numbers).

    A line is executable when it holds a non-whitespace character, covered
    when any of those ran. `executed` is indexed in UTF-16 units.
    """
    executable, missed, offset = 0, [], 0
    for number, line in enumerate(source.split("\n"), start=1):
        has_code = ran = False
        for ch in line:
            width = 2 if ord(ch) > 0xFFFF else 1
            if not ch.isspace():
                has_code = True
                ran = ran or any(executed[offset:offset + width])
            offset += width
        offset += 1  # the "\n"
        if has_code:
            executable += 1
            if not ran:
                missed.append(number)
    return executable, missed


def ranges_text(numbers: list[int]) -> str:
    """[1, 2, 3, 7] -> "1-3, 7", as coverage report -m prints them."""
    parts, start = [], None
    for i, n in enumerate(numbers):
        if start is None:
            start = n
        if i + 1 == len(numbers) or numbers[i + 1] != n + 1:
            parts.append(str(n) if n == start else f"{start}-{n}")
            start = None
    return ", ".join(parts)


def _spin(done, seconds: float) -> bool:
    """Run the Qt event loop until done() or the time is up; True if done."""
    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + seconds
    while not done():
        if time.monotonic() > deadline:
            return False
        QApplication.processEvents()
        time.sleep(0.005)
    return True


class Collector:
    """The DevTools socket, the attached pages, and what ran in each page script."""

    def __init__(self):
        self._sources = {p.name: p.read_text(encoding="utf-8") for p in sorted(WEB_DIR.glob("*.js"))}
        self.executed: dict[str, list[bool]] = {}
        self._sessions: set[str] = set()
        self._wanted: set[int] = set()  # request ids whose reply is read
        self._replies: dict[int, dict] = {}
        self._next_id = 0
        self._ws = None
        self._boot_page = None

    # -- DevTools -------------------------------------------------------- #

    def start(self, app) -> None:
        """Attach to every page from now on. Raises RuntimeError when DevTools is unreachable."""
        from PySide6.QtCore import QUrl
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebSockets import QWebSocket

        # The DevTools server starts only once QtWebEngine is initialised.
        self._boot_page = QWebEnginePage()
        port = os.environ["QTWEBENGINE_REMOTE_DEBUGGING"].rsplit(":", 1)[-1]
        url = self._browser_url(app, f"http://127.0.0.1:{port}/json/version")
        self._ws = QWebSocket()
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.open(QUrl(url))
        if not _spin(self._ws.isValid, 10):
            raise RuntimeError(f"the DevTools socket never opened: {url}")
        reply = self._send(
            "Target.setAutoAttach",
            {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
            want=True,
        )
        if not _spin(lambda: reply in self._replies, 10):
            raise RuntimeError("DevTools never answered Target.setAutoAttach")

    @staticmethod
    def _browser_url(app, url: str, timeout_s: float = 20.0) -> str:
        """The browser target's socket URL, read without blocking the Qt main thread."""
        box = []

        def fetch():
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        box.append(json.load(response)["webSocketDebuggerUrl"])
                    return
                except (OSError, ValueError, KeyError):
                    time.sleep(0.05)

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        while thread.is_alive():
            app.processEvents()
            time.sleep(0.01)
        if not box:
            raise RuntimeError(f"QtWebEngine DevTools never answered at {url}")
        return box[0]

    def _send(
        self, method: str, params: dict | None = None, session: str | None = None, want: bool = False
    ) -> int:
        """Send one DevTools command; with want=True its reply is kept for the caller."""
        self._next_id += 1
        message = {"id": self._next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        if want:
            self._wanted.add(self._next_id)
        self._ws.sendTextMessage(json.dumps(message))
        return self._next_id

    def _on_message(self, text: str) -> None:
        message = json.loads(text)
        if "id" in message:
            if message["id"] in self._wanted:
                self._wanted.discard(message["id"])
                self._replies[message["id"]] = message
            return
        method, params = message.get("method"), message.get("params", {})
        if method == "Target.attachedToTarget":
            session = params["sessionId"]
            if params.get("targetInfo", {}).get("type") == "page":
                self._sessions.add(session)
                self._send("Profiler.enable", session=session)
                self._send(
                    "Profiler.startPreciseCoverage",
                    {"callCount": True, "detailed": True},
                    session,
                )
            # Paused by waitForDebuggerOnStart: without this the page never loads.
            self._send("Runtime.runIfWaitingForDebugger", session=session)
        elif method == "Target.detachedFromTarget":
            self._sessions.discard(params.get("sessionId"))

    def take(self) -> None:
        """Fold what ran since the last take, in every live page, into the file maps.

        ponytail: a view destroyed mid-test loses what ran since the last take
        (an undercount, never an overcount); take on destroy if that matters.
        """
        asked = {
            self._send("Profiler.takePreciseCoverage", session=s, want=True): s
            for s in list(self._sessions)
        }
        _spin(lambda: all(i in self._replies for i in asked), TAKE_TIMEOUT_S)
        for request_id, session in asked.items():
            self._wanted.discard(request_id)
            reply = self._replies.pop(request_id, None)
            if reply is None:
                self._sessions.discard(session)  # gone or hung: stop asking it
                continue
            for script in reply.get("result", {}).get("result", []):
                self._fold(script)

    def _fold(self, script: dict) -> None:
        url = script.get("url", "")
        if not url.startswith("file:"):
            return
        path = Path(urllib.request.url2pathname(urllib.parse.urlparse(url).path)).resolve()
        if path.parent != WEB_DIR or path.name not in self._sources:
            return
        source = self._sources[path.name]
        ran = executed_units(utf16_len(source), script.get("functions", []))
        before = self.executed.get(path.name, [False] * len(ran))
        self.executed[path.name] = [a or b for a, b in zip(before, ran)]

    # -- Report ---------------------------------------------------------- #

    def report(self) -> tuple[list[tuple[str, int, int, str]], float]:
        """Rows of (file, lines, missed, missed ranges) for every gui/web/*.js, and the total %."""
        rows, lines_total, missed_total = [], 0, 0
        for name, source in self._sources.items():
            executed = self.executed.get(name, [False] * utf16_len(source))
            lines, missed = line_report(source, executed)
            rows.append((name, lines, len(missed), ranges_text(missed)))
            lines_total += lines
            missed_total += len(missed)
        cover = 100.0 * (lines_total - missed_total) / lines_total if lines_total else 100.0
        return rows, cover

    def failures(self, threshold: float) -> list[str]:
        """One sentence per file, and for the total, under `threshold` percent."""
        rows, cover = self.report()
        out = [
            f"{name} {100.0 * (lines - missed) / lines:.1f}% < {threshold:g}%"
            for name, lines, missed, _ in rows
            if lines and 100.0 * (lines - missed) / lines < threshold
        ]
        if cover < threshold:
            out.append(f"JS total {cover:.1f}% < {threshold:g}%")
        return out

    def summary_lines(self) -> list[str]:
        rows, cover = self.report()
        width = max(len(name) for name, *_ in rows) if rows else 5
        lines = [f"{'Name':<{width}}  Lines  Miss  Cover  Missing"]
        for name, total, missed, text in rows:
            pct = 100.0 * (total - missed) / total if total else 100.0
            lines.append(f"{name:<{width}}  {total:>5}  {missed:>4}  {pct:>4.0f}%  {text}")
        lines.append(f"{'TOTAL':<{width}}  {'':>5}  {'':>4}  {cover:>4.0f}%")
        return lines
