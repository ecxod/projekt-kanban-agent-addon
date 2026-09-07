#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
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
CHECKSUMS = DIST / "SHA256SUMS"
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
        relative = source.relative_to(ADDON)
        if any(part.startswith(".") for part in relative.parts):
            continue
        add_file(archive, source, relative.as_posix())

source_roots = ["addon", "docs", "native-host", "native-host-windows-wsl", "scripts", "tests"]
source_files = [ROOT / name for name in ["README.md", "INSTALL.md", "PRIVACY.md", "SECURITY.md", "LICENSE", "package.json"]]
for root_name in source_roots:
    source_files.extend(
        path for path in (ROOT / root_name).rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.startswith(".") for part in path.relative_to(ROOT / root_name).parts)
    )
with zipfile.ZipFile(SOURCE, "w") as archive:
    for source in sorted(set(source_files)):
        add_file(archive, source, source.relative_to(ROOT).as_posix())

checksum_lines = []
for artifact in [XPI, SOURCE]:
    checksum_lines.append(f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}")
CHECKSUMS.write_text("\n".join(checksum_lines) + "\n", encoding="ascii")

print(XPI.relative_to(ROOT))
print(SOURCE.relative_to(ROOT))
print(CHECKSUMS.relative_to(ROOT))
