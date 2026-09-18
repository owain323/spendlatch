"""Generate SHA256SUMS.txt — a whole-repo integrity manifest.

Any single-byte change to a tracked file breaks `sha256sum -c` verification.
Regenerate intentionally:  python tools/make_sha256sums.py
Verify:                     python tools/make_sha256sums.py --check
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", "data", ".pytest_cache", ".mypy_cache", "results"}
SKIP_FILES = {"SHA256SUMS.txt"}


def tracked_files() -> list[Path]:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts) or path.name in SKIP_FILES:
            continue
        files.append(rel)
    return files


def digest(rel: Path) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def main() -> int:
    manifest = ROOT / "SHA256SUMS.txt"
    lines = [f"{digest(rel)}  {rel.as_posix()}" for rel in tracked_files()]
    if "--check" in sys.argv:
        if not manifest.exists():
            print("SHA256SUMS.txt missing — run tools/make_sha256sums.py")
            return 1
        expected = manifest.read_text(encoding="utf-8").strip()
        actual = "\n".join(lines)
        if expected == actual:
            print(f"integrity: OK ({len(lines)} files)")
            return 0
        print("integrity: FAILED — working tree differs from the manifest")
        return 1
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {manifest.name}: {len(lines)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
