# Approved mockups (2026-10-08)

Claude Design bundles, made from [`../prompts.md`](../prompts.md) and approved by the owner. They are the
brief for all five phases of the UI refresh (ADR 0002).

| File | Screens | Frames |
|---|---|---|
| `Packer Screens.html` | the index: every frame, importing the files below by name | 1a to 8f |
| `Floor Components.html` | floor-density type, buttons, badges, inputs, rows, banner, toast | 1a, 1b |
| `Packer App.html` | the shell, Packing, Statistics, Sessions, Session details | 2a to 5b, 7a to 8f |
| `Packer Mode.html` | Packer Mode | 6a to 6j |
| `SKU Mapping.html` | SKU mapping | addendum |
| `Worker Selection.html` | Worker selection | addendum |

Do not rename a file: `Packer Screens.html` imports the others by name, and specs cite its frame ids.

## Viewing

Open `Packer Screens.html` in Chrome from this folder. Each frame carries its id; the notes beside a group
are part of the brief.

## Reading exact values

Each file is a bundle: a gzip+base64 manifest of scripts plus a JSON-encoded template. Sizes, colours and
state logic are in the template. The `const T = {...}` table in it holds the tokens as `[light, dark]`
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

Save it outside the repo and run it with `.venv/bin/python -I unpack.py "Packer App.html" /tmp/packer-app`,
then read `/tmp/packer-app/template.html`. The shell is the `<nav>` and `<header>` at the top of that
template; its state logic is `renderVals()` at the bottom.
