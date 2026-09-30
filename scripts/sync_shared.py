"""One-way mirror of the canonical shared/ package from
shopify-fulfillment-tool into this repo. shopify-fulfillment-tool/shared/ is
the single source of truth (its docs/adr/0017-fulfilment-owns-shared.md) —
never hand-edit packing-tool/shared/ directly.

Usage:
    python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool] [--force]

The path is only needed from a git worktree, where the sibling-directory
default does not resolve. Only files git tracks are copied. A source whose HEAD
does not contain the previously synced commit (a stale or diverged checkout)
is refused, since syncing it would roll shared/ back; --force overrides that. The copied commit is written to
scripts/shared_synced_from.txt, and CI checks shared/ against the source repo
at that commit, so this repo may lag behind for as long as it likes.
"""
import shutil
import subprocess
import sys
from pathlib import Path

THIS_REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = THIS_REPO.parent / "shopify-fulfillment-tool"
DEST = THIS_REPO / "shared"
PIN = THIS_REPO / "scripts" / "shared_synced_from.txt"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    root = Path(argv[0]).expanduser().resolve() if argv else DEFAULT_SOURCE
    source = root / "shared"

    if not source.is_dir():
        print(f"Source not found: {source}", file=sys.stderr)
        if not argv:
            print(
                "Expected shopify-fulfillment-tool as a sibling directory of "
                "this repo, or pass its path as an argument.",
                file=sys.stderr,
            )
        return 1

    try:
        dirty = _git(root, "status", "--porcelain", "--", "shared")
        sha = _git(root, "rev-parse", "HEAD").strip()
        branch = _git(root, "branch", "--show-current").strip() or "detached HEAD"
        tracked = [f for f in _git(root, "ls-files", "-z", "--", "shared").split("\0") if f]
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"{root} is not a usable git checkout: {exc}", file=sys.stderr)
        return 1
    if dirty:
        print(
            f"{source} has uncommitted or untracked changes; commit them first "
            f"so the recorded commit matches what is copied:\n{dirty}",
            file=sys.stderr,
        )
        return 1

    old = PIN.read_text(encoding="utf-8").strip() if PIN.exists() else ""
    if old and not force:
        ancestor = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", old, "HEAD"],
            capture_output=True, check=False,
        )
        if ancestor.returncode != 0:
            print(
                f"{root} ({branch}) at {sha} does not contain the last synced commit "
                f"{old}: syncing would roll shared/ back. Fetch and check out the "
                "source's main, or pass --force if that is intended.",
                file=sys.stderr,
            )
            return 1

    if DEST.exists():
        shutil.rmtree(DEST)
    for rel in tracked:
        target = DEST / Path(rel).relative_to("shared")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    PIN.write_text(sha + "\n", encoding="utf-8")

    count = sum(1 for p in DEST.rglob("*") if p.is_file())
    print(f"Synced {count} file(s) from {source} ({branch}) at {sha} into {DEST}.")
    print("Push that commit before opening a PR: CI checks out the source at it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
