# Approved mockups (2026-09-30)

Claude Design bundles, made from [`../prompts.md`](../prompts.md) and approved by the owner. The phase that
builds each screen is listed in [`../roadmap.md`](../roadmap.md).

| File | Screen |
|---|---|
| `app-shell.html` | Sidebar, command bar, connection states |
| `setup.html` | Setup |
| `results.html` | Results |
| `browse.html` | Browse |
| `logs.html` | Logs |
| `tools.html` | Tools |
| `client-settings.html` | Client settings window |
| `component-sheet.html` | Tokens, type scale, buttons, badges, inputs, states |

`renders/<file>.png` shows the default state in light mode at 1440×1000.

## Viewing

Open a file in Chrome. The dark strip at the top switches states and themes. The dark panel at the bottom holds
the design notes, and they are part of the brief.

A new render of a state:

```bash
google-chrome --headless=new --hide-scrollbars --virtual-time-budget=8000 \
  --window-size=1440,1000 --screenshot=out.png "file://$PWD/app-shell.html"
```

## Reading exact values

Each file is a bundle: a gzip+base64 manifest of scripts plus a JSON-encoded template. Sizes, colours and
state logic are in the template. The `const T = {...}` table at its end holds the tokens as `[light, dark]`
pairs. To unpack:

```python
import base64, gzip, json, re, sys
from pathlib import Path

src = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
block = lambda t: re.search(rf'<script type="__bundler/{t}">(.*?)</script>', src, re.S).group(1)
for key, entry in json.loads(block("manifest")).items():
    data = base64.b64decode(entry["data"])
    (out / f"{key}.js").write_bytes(gzip.decompress(data) if entry.get("compressed") else data)
(out / "template.html").write_text(json.loads(block("template")))
```

Run it with `.venv/bin/python unpack.py app-shell.html /tmp/app-shell`, then read `/tmp/app-shell/template.html`.
