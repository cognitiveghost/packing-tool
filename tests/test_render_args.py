"""The render scripts' one shared piece: where to write, and at what size."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_args import parse_args

FINAL = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "final"


def test_the_default_is_the_floor_size_into_its_own_folder():
    assert parse_args([]) == (FINAL / "1366x768", 1366, 768)


def test_a_size_picks_its_folder():
    assert parse_args(["--size", "1920x1080"]) == (FINAL / "1920x1080", 1920, 1080)


def test_an_explicit_folder_wins(tmp_path):
    assert parse_args([str(tmp_path), "--size", "1920X1080"]) == (tmp_path, 1920, 1080)


@pytest.mark.parametrize("size", ["1366", "axb", "0x768", "1366x"])
def test_a_size_that_is_not_two_positive_numbers_is_refused(size):
    with pytest.raises(SystemExit):
        parse_args(["--size", size])
