#!/usr/bin/env python3
"""Idempotent, anchored in-place patcher for the 2026-06-12 security hotfix.

Applies M1 (context-upload path sanitisation) to app/main.py and L1 (hardened
SECRET_KEY guard) to app/database.py. Edits ONLY the exact anchor lines, leaving
all other server-side content untouched. Backs up both files first. Safe to run
twice (detects already-applied state and no-ops).

Usage:  python3 apply_hotfix_inplace.py /opt/calltone-backend
Exit 0 = applied or already-applied; non-zero = nothing changed unexpectedly.
"""
import sys, time, py_compile
from pathlib import Path

base = Path(sys.argv[1])
main_py = base / "app" / "main.py"
db_py = base / "app" / "database.py"
ts = time.strftime("%Y%m%d-%H%M%S")

M1_OLD = (
    '    tmp_path = UPLOAD_DIR / f"context_{company_name.lower().replace(\' \', \'_\')}'
    '_{uuid.uuid4().hex[:8]}.txt"'
)
M1_NEW = (
    '    safe_company = _sanitize_filename(company_name.lower().replace(" ", "_"))\n'
    '    tmp_path = UPLOAD_DIR / f"context_{safe_company}_{uuid.uuid4().hex[:8]}.txt"'
)
L1_OLD = "if not settings.DEBUG and settings.SECRET_KEY == _DEV_SECRET_KEY_DEFAULT:"
L1_NEW = (
    "if settings.SECRET_KEY == _DEV_SECRET_KEY_DEFAULT and ("
    "not settings.DEBUG or not settings.use_sqlite):"
)


def patch(path, old, new, already_marker):
    text = path.read_text(encoding="utf-8")
    if already_marker in text:
        print(f"[skip] {path.name}: already patched")
        return False
    n = text.count(old)
    if n != 1:
        print(f"[ABORT] {path.name}: expected exactly 1 anchor, found {n}. No change.")
        sys.exit(3)
    path.with_suffix(path.suffix + f".bak-{ts}").write_text(text, encoding="utf-8")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[ok] {path.name}: patched (backup .bak-{ts})")
    return True


patch(main_py, M1_OLD, M1_NEW, already_marker="safe_company = _sanitize_filename")
patch(db_py, L1_OLD, L1_NEW, already_marker="not settings.use_sqlite")

for p in (main_py, db_py):
    py_compile.compile(str(p), doraise=True)
print("[ok] py_compile passed for both files")
