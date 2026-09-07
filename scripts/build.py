#!/usr/bin/env python3
from __future__ import annotations

import json
import gzip
import hashlib
import io
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon"
DIST = ROOT / "dist"
MANIFEST = json.loads((ADDON / "manifest.json").read_text(encoding="utf-8"))
VERSION = MANIFEST["version"]
XPI = DIST / f"projekt-kanban-agent-{VERSION}.xpi"
SOURCE = DIST / f"projekt-kanban-agent-{VERSION}-source.zip"
BUNDLE = DIST / f"projekt-kanban-agent-{VERSION}-linux.tar.gz"
CHECKSUMS = DIST / "SHA256SUMS"
FIXED_TIME = (2026, 9, 7, 0, 0, 0)
FIXED_EPOCH = 1788739200


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
source_files = [ROOT / name for name in ["README.md", "INSTALL.md", "PRIVACY.md", "SECURITY.md", "LICENSE", "package.json"]]
for root_name in source_roots:
    source_files.extend(path for path in (ROOT / root_name).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
with zipfile.ZipFile(SOURCE, "w") as archive:
    for source in sorted(set(source_files)):
        add_file(archive, source, source.relative_to(ROOT).as_posix())

bundle_root = f"projekt-kanban-agent-{VERSION}"
bundle_files = [
    (XPI, XPI.name, 0o644),
    (ROOT / "INSTALL.md", "INSTALL.md", 0o644),
    (ROOT / "README.md", "README.md", 0o644),
    (ROOT / "LICENSE", "LICENSE", 0o644),
]
for source in sorted(path for path in (ROOT / "native-host").rglob("*") if path.is_file() and "__pycache__" not in path.parts):
    mode = 0o755 if source.suffix in {".py", ".sh"} else 0o644
    bundle_files.append((source, source.relative_to(ROOT).as_posix(), mode))

with BUNDLE.open("wb") as raw_handle:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
        with tarfile.open(fileobj=gzip_handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for source, relative, mode in bundle_files:
                data = source.read_bytes()
                info = tarfile.TarInfo(f"{bundle_root}/{relative}")
                info.size = len(data)
                info.mode = mode
                info.mtime = FIXED_EPOCH
                info.uid = 0
                info.gid = 0
                info.uname = "root"
                info.gname = "root"
                archive.addfile(info, io.BytesIO(data))

checksum_lines = []
for artifact in [XPI, SOURCE, BUNDLE]:
    checksum_lines.append(f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}")
CHECKSUMS.write_text("\n".join(checksum_lines) + "\n", encoding="ascii")

print(XPI.relative_to(ROOT))
print(SOURCE.relative_to(ROOT))
print(BUNDLE.relative_to(ROOT))
print(CHECKSUMS.relative_to(ROOT))
