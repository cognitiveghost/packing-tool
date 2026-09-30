"""scripts/sync_shared.py mirrors shopify-fulfillment-tool/shared/ into this
repo and pins the commit it copied, which CI checks shared/ against."""
import subprocess

import pytest

from scripts import sync_shared


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def source(tmp_path):
    """A committed fake Fulfilment checkout, with the same __pycache__
    ignore the real one has."""
    root = tmp_path / "fulfilment"
    (root / "shared" / "components").mkdir(parents=True)
    (root / "shared" / "theme.py").write_text("X = 1\n", encoding="utf-8")
    (root / "shared" / "components" / "card.py").write_text("Y = 2\n", encoding="utf-8")
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def dest(tmp_path, monkeypatch):
    """This repo's side: a shared/ holding a file the source no longer has."""
    shared = tmp_path / "packing" / "shared"
    shared.mkdir(parents=True)
    (shared / "stale.py").write_text("old\n", encoding="utf-8")
    pin = tmp_path / "packing" / "shared_synced_from.txt"
    monkeypatch.setattr(sync_shared, "DEST", shared)
    monkeypatch.setattr(sync_shared, "PIN", pin)
    return shared, pin


def _files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_mirrors_the_source_and_pins_its_commit(source, dest):
    shared, pin = dest
    cache = source / "shared" / "__pycache__"
    cache.mkdir()
    (cache / "theme.cpython-314.pyc").write_bytes(b"\0")

    assert sync_shared.main([str(source)]) == 0

    assert _files(shared) == ["components/card.py", "theme.py"]
    assert (shared / "theme.py").read_text(encoding="utf-8") == "X = 1\n"
    assert pin.read_text(encoding="utf-8") == _git(source, "rev-parse", "HEAD") + "\n"


def test_a_modified_source_is_refused_and_nothing_changes(source, dest):
    shared, pin = dest
    (source / "shared" / "theme.py").write_text("X = 2\n", encoding="utf-8")

    assert sync_shared.main([str(source)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_an_untracked_file_in_the_source_counts_as_dirty(source, dest):
    shared, pin = dest
    (source / "shared" / "new_module.py").write_text("Z = 3\n", encoding="utf-8")

    assert sync_shared.main([str(source)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_a_source_that_is_not_a_git_checkout_is_refused(tmp_path, dest):
    shared, pin = dest
    plain = tmp_path / "plain"
    (plain / "shared").mkdir(parents=True)
    (plain / "shared" / "theme.py").write_text("X = 1\n", encoding="utf-8")

    assert sync_shared.main([str(plain)]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()


def test_a_missing_source_is_refused(tmp_path, dest):
    shared, pin = dest

    assert sync_shared.main([str(tmp_path / "nowhere")]) == 1

    assert _files(shared) == ["stale.py"]
    assert not pin.exists()
