"""Generate SHA256SUMS.txt — a whole-repo integrity manifest.

Any single-byte change to a tracked file breaks `sha256sum -c` verification.
Regenerate intentionally:  python tools/make_sha256sums.py
Verify:                     python tools/make_sha256sums.py --check
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", "data", ".pytest_cache", ".mypy_cache", "results"}
SKIP_FILES = {"SHA256SUMS.txt"}


def tracked_files() -> list[Path]:
    # Prefer git-tracked files: the manifest must match exactly what a fresh
    # clone (and the CI checkout) contains, not whatever work-in-progress
    # files happen to sit in the working tree. Fall back to a directory
    # scan only when git is unavailable (e.g. the repo was copied as files).
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        names = sorted(n for n in out.decode("utf-8").split("\0") if n)
        if names:
            return [Path(n) for n in names if Path(n).name not in SKIP_FILES]
    except (OSError, subprocess.CalledProcessError):
        pass
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


def check_line_endings(files: list[Path]) -> int:
    # Git stores LF (see .gitattributes), so the working tree must be LF
    # too — otherwise the manifest hashes CRLF bytes that no fresh clone
    # or CI checkout will ever reproduce.
    bad = []
    for rel in files:
        try:
            if b"\r\n" in (ROOT / rel).read_bytes():
                bad.append(rel.as_posix())
        except OSError:
            pass
    if bad:
        print("CRLF line endings detected (convert these files to LF):")
        print("\n".join(f"  {f}" for f in bad))
        return 1
    return 0


def main() -> int:
    manifest = ROOT / "SHA256SUMS.txt"
    files = tracked_files()
    if check_line_endings(files):
        return 1
    lines = [f"{digest(rel)}  {rel.as_posix()}" for rel in files]
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
