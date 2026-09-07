#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MANIFEST = json.loads((ROOT / "addon" / "manifest.json").read_text(encoding="utf-8"))
VERSION = MANIFEST["version"]
UNSIGNED_XPI = DIST / f"projekt-kanban-agent-{VERSION}.xpi"
SIGNED_XPI = DIST / f"projekt-kanban-agent-{VERSION}-signed.xpi"
SOURCE = DIST / f"projekt-kanban-agent-{VERSION}-source.zip"
BUNDLE = DIST / f"projekt-kanban-agent-{VERSION}-linux.tar.gz"
CHECKSUMS = DIST / "SHA256SUMS"
FIXED_EPOCH = 1788739200
SIGNATURE_FILES = {
    "META-INF/cose.manifest", "META-INF/cose.sig", "META-INF/manifest.mf",
    "META-INF/mozilla.sf", "META-INF/mozilla.rsa"
}


def verify_signed_xpi() -> None:
    with zipfile.ZipFile(UNSIGNED_XPI) as unsigned, zipfile.ZipFile(SIGNED_XPI) as signed:
        unsigned_names = set(unsigned.namelist())
        signed_names = set(signed.namelist())
        if signed_names - unsigned_names != SIGNATURE_FILES:
            raise SystemExit("Signed XPI does not contain the expected Mozilla signature files.")
        for name in unsigned_names:
            if name == "manifest.json":
                if json.loads(unsigned.read(name)) != json.loads(signed.read(name)):
                    raise SystemExit("Signed manifest differs semantically from the source manifest.")
            elif unsigned.read(name) != signed.read(name):
                raise SystemExit(f"Signed XPI content differs from source: {name}")


def bundle_file(archive: tarfile.TarFile, source: Path, relative: str, mode: int) -> None:
    data = source.read_bytes()
    info = tarfile.TarInfo(f"projekt-kanban-agent-{VERSION}/{relative}")
    info.size = len(data)
    info.mode = mode
    info.mtime = FIXED_EPOCH
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    archive.addfile(info, io.BytesIO(data))


verify_signed_xpi()
files = [
    (SIGNED_XPI, SIGNED_XPI.name, 0o644),
    (ROOT / "INSTALL.md", "INSTALL.md", 0o644),
    (ROOT / "README.md", "README.md", 0o644),
    (ROOT / "LICENSE", "LICENSE", 0o644),
]
for source in sorted(path for path in (ROOT / "native-host").rglob("*") if path.is_file() and "__pycache__" not in path.parts):
    files.append((source, source.relative_to(ROOT).as_posix(), 0o755 if source.suffix in {".py", ".sh"} else 0o644))

with BUNDLE.open("wb") as raw_handle:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
        with tarfile.open(fileobj=gzip_handle, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for source, relative, mode in files:
                bundle_file(archive, source, relative, mode)

artifacts = [SIGNED_XPI, SOURCE, BUNDLE]
CHECKSUMS.write_text("\n".join(
    f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.name}"
    for artifact in artifacts
) + "\n", encoding="ascii")

print(BUNDLE.relative_to(ROOT))
print(CHECKSUMS.relative_to(ROOT))
