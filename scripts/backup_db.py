#!/usr/bin/env python3
"""Backup legal.db — копия с датой в backup/. Запускать cron'ом."""
import shutil
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "legal.db"
DST_DIR = Path(__file__).resolve().parent.parent / "backup"

if not SRC.exists():
    print(f"DB not found: {SRC}")
    sys.exit(0)

DST_DIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
dst = DST_DIR / f"legal_{stamp}.db"
shutil.copy2(SRC, dst)
print(f"Backup: {SRC} -> {dst}")
