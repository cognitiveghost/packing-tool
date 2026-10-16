"""The render scripts' one shared piece: where to write, and at what size."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_args import parse_args

FINAL = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "final"


def test_the_default_is_the_floor_size_into_its_own_folder():
    assert parse_args([]) == (FINAL / "1366x768", 1366, 768, "en")


def test_a_size_picks_its_folder():
    assert parse_args(["--size", "1920x1080"]) == (FINAL / "1920x1080", 1920, 1080, "en")


def test_an_explicit_folder_wins(tmp_path):
    assert parse_args([str(tmp_path), "--size", "1920X1080"]) == (tmp_path, 1920, 1080, "en")


def test_a_language_is_picked_by_code():
    assert parse_args(["--lang", "bg"])[3] == "bg"


def test_an_unknown_language_is_refused():
    with pytest.raises(SystemExit):
        parse_args(["--lang", "xx"])


@pytest.mark.parametrize("size", ["1366", "axb", "0x768", "1366x"])
def test_a_size_that_is_not_two_positive_numbers_is_refused(size):
    with pytest.raises(SystemExit):
        parse_args(["--size", size])
