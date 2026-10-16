"""The Packing Tool user guide's Markdown: its screenshots exist and are all used.

Only `re` and `pathlib`: the build (shared.guide.build) needs a PDF engine this
repo's CI does not install, so nothing here imports it.
"""

import re
from pathlib import Path

USER_GUIDE_DIR = Path(__file__).resolve().parents[1] / "docs" / "user-guide"
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def test_guide_images_exist():
    assert (USER_GUIDE_DIR / "en.md").is_file()
    for guide in (USER_GUIDE_DIR / "en.md", USER_GUIDE_DIR / "bg.md"):
        if not guide.is_file():
            continue
        for src in _IMAGE_RE.findall(guide.read_text(encoding="utf-8")):
            assert (USER_GUIDE_DIR / src).is_file(), f"{guide.name} points at missing {src}"


def test_guide_uses_every_screenshot():
    text = (USER_GUIDE_DIR / "en.md").read_text(encoding="utf-8")
    shots = {path.name for path in (USER_GUIDE_DIR / "img" / "en").glob("*.png")}
    used = {Path(src).name for src in _IMAGE_RE.findall(text)}
    assert shots - used == set()


def test_guide_bg_matches_en():
    en = (USER_GUIDE_DIR / "en.md").read_text(encoding="utf-8")
    bg_path = USER_GUIDE_DIR / "bg.md"
    assert bg_path.is_file()
    bg = bg_path.read_text(encoding="utf-8")
    en_srcs = _IMAGE_RE.findall(en)
    bg_srcs = _IMAGE_RE.findall(bg)
    assert [Path(src).name for src in bg_srcs] == [Path(src).name for src in en_srcs]
    assert all(src.startswith("img/bg/") for src in bg_srcs)
    assert all(src.startswith("img/en/") for src in en_srcs)
    for prefix in ("## ", "### "):
        en_count = sum(line.startswith(prefix) for line in en.splitlines())
        bg_count = sum(line.startswith(prefix) for line in bg.splitlines())
        assert bg_count == en_count, f"{prefix!r} headings: bg {bg_count} vs en {en_count}"
