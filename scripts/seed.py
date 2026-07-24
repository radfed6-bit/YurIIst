#!/usr/bin/env python3
"""Загрузка официальных текстов кодексов РФ в БД."""
import subprocess, sys
sys.exit(subprocess.call([sys.executable, "download_official.py"]))
