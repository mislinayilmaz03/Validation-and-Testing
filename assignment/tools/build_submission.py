"""Assemble the markdown documents in docs/ into the single submitted PDF.

The repository is the primary deliverable; this produces the one document that is
handed in alongside the repository link. Keeping the build in a script means the PDF is
regenerated from the same sources a reviewer reads on GitHub, so the two cannot diverge.

Usage: .venv/Scripts/python.exe tools/build_submission.py
"""
from __future__ import annotations

import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT_PDF = ROOT / "reports" / "SOFT411-Split-Payment-Report.pdf"

# Reading order of the submitted document.
SECTIONS = [
    "COVER.md",
    "EVIDENCE.md",
    "TECHNICAL-REPORT.md",
    "TEST-CASES.md",
    "SECURITY-TRIAGE.md",
    "REFLECTION.md",
]

# No nl2br: the sources are hard-wrapped at ~88 columns, and turning every source
# newline into a <br> would break running prose mid-sentence in the PDF. Documents that
# genuinely need a line break use a markdown hard break (two trailing spaces).
MD_EXTENSIONS = ["tables", "fenced_code", "sane_lists", "attr_list"]

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.5; color: #1b1f24; }
h1 { font-size: 19pt; margin: 0 0 6pt; color: #0b2545; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; color: #0b2545;
     border-bottom: 1px solid #c8d2dd; padding-bottom: 3pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; color: #163a5f; }
h1, h2, h3 { page-break-after: avoid; }
p, li { orphans: 2; widows: 2; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9pt;
        page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #c8d2dd; padding: 3.5pt 5pt; text-align: left;
         vertical-align: top; }
th { background: #eef2f7; font-weight: 600; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt;
       background: #f2f4f7; padding: 0.5pt 2.5pt; border-radius: 2px; }
pre { background: #f6f8fa; border: 1px solid #d8dee4; border-radius: 3px;
      padding: 7pt 9pt; font-size: 8.5pt; line-height: 1.4; overflow-wrap: break-word;
      white-space: pre-wrap; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
blockquote { margin: 8pt 0; padding: 5pt 10pt; border-left: 3px solid #9fb3c8;
             background: #f7f9fb; color: #39414a; }
img { max-width: 100%; border: 1px solid #c8d2dd; border-radius: 2px;
      display: block; margin: 8pt auto 3pt; page-break-inside: avoid; }
hr { border: none; border-top: 1px solid #c8d2dd; margin: 12pt 0; }
.missing { border: 1px dashed #b0bac5; border-radius: 3px; background: #fbfcfd;
           color: #6b7682; font-size: 9pt; text-align: center; padding: 16pt 10pt;
           margin: 8pt 0 3pt; }
.pagebreak { page-break-after: always; }
.section { page-break-before: always; }
.section:first-of-type { page-break-before: avoid; }
"""

HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head>
<body>{body}</body></html>
"""

FOOTER = """
<div style="width:100%; font-family:'Segoe UI',Arial,sans-serif; font-size:7.5pt;
            color:#6b7682; padding:0 16mm; display:flex; justify-content:space-between;">
  <span>SOFT411 — Split Payment: Modern Testing Strategy &amp; Prototype</span>
  <span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>
"""


def absolutise_images(html: str, base: Path) -> str:
    """Point every relative <img src> at a file:// URL.

    The HTML is rendered from a temporary location, so relative paths such as
    ../reports/screenshots/... would otherwise resolve to nothing and the figures
    would silently come out blank.
    """

    def repl(match: re.Match[str]) -> str:
        src = match.group(2)
        if re.match(r"^(https?:|data:|file:)", src):
            return match.group(0)
        resolved = (base / src).resolve()
        if not resolved.exists():
            # A broken-image icon in a submitted PDF looks like a mistake; an explicit
            # placeholder states what is still missing and where it belongs.
            print(f"  ! missing image: {src}")
            return (
                '<div class="missing">Figure not captured yet — '
                f"<code>{src.split('/')[-1]}</code></div>"
            )
        return f"{match.group(1)}{resolved.as_uri()}{match.group(3)}"

    # Group 3 spans the rest of the tag, so a missing image can be replaced whole
    # instead of leaving the tag's tail behind in the output.
    return re.sub(r'(<img\b[^>]*?\ssrc=")([^"]+)("[^>]*>)', repl, html)


def render_sections() -> str:
    parts: list[str] = []
    for name in SECTIONS:
        source = DOCS / name
        text = source.read_text(encoding="utf-8")
        # Honour the explicit page breaks the documents already carry.
        text = text.replace("<!--PAGEBREAK-->", '<div class="pagebreak"></div>')
        body = markdown.markdown(text, extensions=MD_EXTENSIONS)
        parts.append(f'<div class="section">{absolutise_images(body, source.parent)}</div>')
        print(f"  + {name}")
    return "\n".join(parts)


def main() -> int:
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    document = HTML_TEMPLATE.format(
        title="SOFT411 — Split Payment Testing Report", css=CSS, body=render_sections()
    )
    staged = OUT_PDF.with_suffix(".html")
    staged.write_text(document, encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(staged.as_uri(), wait_until="load")
        page.pdf(
            path=str(OUT_PDF),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=FOOTER,
            margin={"top": "14mm", "bottom": "16mm", "left": "0", "right": "0"},
        )
        browser.close()

    staged.unlink()
    print(f"  wrote {OUT_PDF.relative_to(ROOT).as_posix()}  ({OUT_PDF.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
