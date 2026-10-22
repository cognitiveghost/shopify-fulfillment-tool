"""Builds a user guide PDF from its Markdown source. Shared by Fulfilment and Packing Tool.

`markdown` and `weasyprint` are imported inside the functions, so the frozen app never pulls them in.

    python -m shared.guide.build <guide.md> [--out <file.pdf>]
"""

from __future__ import annotations

import argparse
import datetime
import html
import re
import subprocess
from pathlib import Path

from shared.theme import LIGHT_THEME

_CSS_PATH = Path(__file__).with_name("guide.css")
_TOC_TITLE = {"bg": "Съдържание"}
_IMG_RE = re.compile(r'<p><img alt="([^"]*)" src="([^"]+)" ?/></p>')
_SRC_RE = re.compile(r'<img[^>]*src="([^"]+)"')
_H1_RE = re.compile(r"<h1[^>]*>.*?</h1>", re.DOTALL)


def _css() -> str:
    tokens = {
        "--accent": LIGHT_THEME.accent_fill,
        "--text": LIGHT_THEME.text,
        "--text-secondary": LIGHT_THEME.text_secondary,
        "--border": LIGHT_THEME.border_subtle,
        "--surface-sunken": LIGHT_THEME.surface_sunken,
    }
    root = ":root { " + " ".join(f"{name}: {value};" for name, value in tokens.items()) + " }"
    return root + "\n" + _CSS_PATH.read_text(encoding="utf-8")


def _git_commit(folder: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=folder, capture_output=True, text=True, check=False
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def build_html(md_path: Path) -> str:
    """Return the guide as one HTML document. Raises FileNotFoundError for a missing image."""
    import markdown

    md_path = Path(md_path)
    lang = md_path.stem
    text = md_path.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["extra", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-3"}},
    )
    body = md.convert(text)
    for src in _SRC_RE.findall(body):
        if not (md_path.parent / src).is_file():
            raise FileNotFoundError(f"image not found in guide: {src}")

    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else md_path.stem
    body = _H1_RE.sub("", body, count=1)  # the cover carries the title
    body = _IMG_RE.sub(r'<figure><img alt="\1" src="\2"><figcaption>\1</figcaption></figure>', body)

    today = datetime.datetime.now(datetime.UTC).astimezone().date().isoformat()
    meta = [lang, today, _git_commit(md_path.parent)]
    contents = _TOC_TITLE.get(lang, "Contents")
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{_css()}</style></head><body>"
        f'<section class="cover"><h1>{html.escape(title)}</h1>'
        f'<p class="cover-meta">{html.escape(" · ".join(part for part in meta if part))}</p></section>'
        f'<nav class="toc"><p class="toc-title">{contents}</p>{md.toc}</nav>'
        f"<main>{body}</main></body></html>"
    )


def build_pdf(md_path: Path, out: Path | None = None) -> Path:
    """Write the guide as a PDF and return its path. Default output sits beside the Markdown file."""
    import weasyprint

    md_path = Path(md_path)
    out = Path(out) if out else md_path.with_suffix(".pdf")
    weasyprint.HTML(string=build_html(md_path), base_url=str(md_path.parent)).write_pdf(out)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a user guide PDF from Markdown.")
    parser.add_argument("guide", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    print(build_pdf(args.guide, args.out))


if __name__ == "__main__":
    main()
