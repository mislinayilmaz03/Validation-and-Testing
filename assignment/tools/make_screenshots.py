"""Render the committed evidence in reports/ as PNG screenshots for the submission.

The screenshots are generated from the artefacts of the recorded test run, not from a
fresh run, so what the report shows and what reports/ contains cannot drift apart.
The only screenshot that cannot be produced here is the CI run (06-ci-run.png): it
only exists once the repository is pushed and GitHub Actions has executed the workflow.

Usage: .venv/Scripts/python.exe tools/make_screenshots.py
"""
from __future__ import annotations

import html
import socket
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = REPORTS / "screenshots"
VIEWPORT = {"width": 1280, "height": 900}

# A terminal-ish frame, so a console capture is recognisable as console output.
CONSOLE_TEMPLATE = """<!doctype html>
<meta charset="utf-8">
<style>
  body {{ margin: 0; background: #ffffff; font-family: Consolas, "Courier New", monospace; }}
  #term {{ background: #1d2027; padding-bottom: 10px; }}
  .bar {{ background: #2b2f3a; color: #c9d1d9; padding: 8px 14px; font-size: 13px;
          border-bottom: 1px solid #11141a; }}
  .dot {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%;
          margin-right: 6px; vertical-align: middle; }}
  pre {{ margin: 0; padding: 16px 18px; color: #d7dae0; font-size: 13px; line-height: 1.5;
         white-space: pre-wrap; word-break: break-word; }}
  .cmd {{ color: #7ee787; }}
</style>
<div id="term">
  <div class="bar">
    <span class="dot" style="background:#ff5f56"></span>
    <span class="dot" style="background:#ffbd2e"></span>
    <span class="dot" style="background:#27c93f"></span>
    {title}
  </div>
  <pre><span class="cmd">$ {command}</span>

{body}</pre>
</div>
"""


def read_text(path: Path) -> str:
    """Report artefacts were written by a Windows console, so cp1254 is the fallback."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1254", errors="replace")


def console_png(page, out_name: str, title: str, command: str, body: str) -> Path:
    page.set_content(
        CONSOLE_TEMPLATE.format(
            title=html.escape(title), command=html.escape(command), body=html.escape(body.strip())
        )
    )
    # Capture the terminal element rather than the page: a ten-line transcript on a
    # 900 px viewport would otherwise be mostly empty background in the report.
    target = OUT / out_name
    page.locator("#term").screenshot(path=str(target))
    return target


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def swagger_png(page) -> Path | None:
    """Start the service and capture the live API surface (OpenAPI UI)."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
    )
    try:
        for _ in range(60):
            if proc.poll() is not None:
                print("  ! uvicorn exited early, skipping Swagger capture")
                return None
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.25)
        else:
            print("  ! service did not start in time, skipping Swagger capture")
            return None

        page.goto(f"http://127.0.0.1:{port}/docs", wait_until="load")
        page.wait_for_selector(".opblock", timeout=15_000)
        page.wait_for_timeout(600)  # let the fonts and the schema panel settle
        target = OUT / "02-api-swagger-ui.png"
        page.locator(".swagger-ui").screenshot(path=str(target))
        return target
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def html_report_png(page) -> Path | None:
    """Capture the pytest HTML report with its result rows rendered.

    The report builds its table from an embedded ES module, which a browser refuses to
    execute over file:// (module scripts are blocked for opaque origins). Serving
    reports/ over loopback for the duration of the capture is what makes the 34 rows
    appear instead of an empty table.
    """
    report = REPORTS / "test-report.html"
    if not report.exists():
        return None

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(REPORTS))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}/test-report.html", wait_until="load")
        try:
            page.wait_for_selector("#results-table tbody tr", timeout=15_000)
        except PlaywrightTimeout:
            print("  ! result rows did not render, capturing the summary only")
        page.wait_for_timeout(500)
        target = OUT / "01-pytest-html-report.png"
        page.screenshot(path=str(target), full_page=True)
        return target
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)

        # 1. the pytest HTML report, as generated by the recorded run
        if (report := html_report_png(page)) is not None:
            made.append(report)

        # 2. the running service
        if (swagger := swagger_png(page)) is not None:
            made.append(swagger)

        # 3-5. console artefacts
        captures = [
            (
                "03-pytest-console.png",
                "pytest — 34 passed",
                "pytest --html=reports/test-report.html --self-contained-html",
                REPORTS / "pytest-console.txt",
            ),
            (
                "04-bandit-sast.png",
                "Bandit SAST — 0 findings",
                "bandit -r app -c bandit.yaml --severity-level medium",
                REPORTS / "bandit.txt",
            ),
            (
                "05-defect-injection.png",
                "Defect injection — 3 of 3 caught",
                "python tools/defect_injection.py",
                REPORTS / "defect-injection.json",
            ),
        ]
        for out_name, title, command, source in captures:
            if source.exists():
                made.append(console_png(page, out_name, title, command, read_text(source)))

        browser.close()

    for path in made:
        print(f"  wrote {path.relative_to(ROOT).as_posix()}  ({path.stat().st_size // 1024} KB)")
    missing = OUT / "06-ci-run.png"
    if not missing.exists():
        print(f"  ! {missing.relative_to(ROOT).as_posix()} still missing — capture the GitHub Actions run manually")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
