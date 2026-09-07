#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
DIST = ROOT / "dist"
MANIFEST = json.loads((ADDON / "manifest.json").read_text(encoding="utf-8"))
VERSION = MANIFEST["version"]
XPI = DIST / f"projekt-kanban-agent-{VERSION}.xpi"
SOURCE = DIST / f"projekt-kanban-agent-{VERSION}-source.zip"
FIXED_TIME = (2026, 9, 7, 0, 0, 0)


def add_file(archive: zipfile.ZipFile, source: Path, name: str) -> None:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(info, source.read_bytes())


subprocess.run(["python3", str(ROOT / "scripts" / "validate.py")], check=True)
DIST.mkdir(exist_ok=True)

with zipfile.ZipFile(XPI, "w") as archive:
    for source in sorted(path for path in ADDON.rglob("*") if path.is_file()):
        add_file(archive, source, source.relative_to(ADDON).as_posix())

source_roots = ["addon", "docs", "native-host", "scripts", "tests"]
source_files = [ROOT / name for name in ["README.md", "PRIVACY.md", "SECURITY.md", "LICENSE", "package.json"]]
for root_name in source_roots:
    source_files.extend(path for path in (ROOT / root_name).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
with zipfile.ZipFile(SOURCE, "w") as archive:
    for source in sorted(set(source_files)):
        add_file(archive, source, source.relative_to(ROOT).as_posix())

print(XPI.relative_to(ROOT))
print(SOURCE.relative_to(ROOT))
