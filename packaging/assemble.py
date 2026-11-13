#!/usr/bin/env python3
"""Assemble a deterministic, self-contained Tendboat agent plugin archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from verify import verify


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_archive(source: Path, output: Path, top: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in [source, *sorted(source.rglob("*"))]:
            relative = Path(top) / path.relative_to(source)
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if path.is_file():
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                archive.addfile(info)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
            compressed.write(buffer.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tendboat-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.tendboat_binary.resolve()
    lock = json.loads((ROOT / "tendboat.lock.json").read_text(encoding="utf-8"))
    if not binary.is_file() or sha256(binary) != lock["binary_sha256"]:
        raise SystemExit("Tendboat binary is missing or does not match tendboat.lock.json")
    with tempfile.TemporaryDirectory(prefix="tendboat-plugin-") as raw:
        staged = Path(raw) / "plugin"
        shutil.copytree(ROOT / "plugin", staged, ignore=shutil.ignore_patterns("bin"))
        target = staged / "bin/tendboat"
        target.parent.mkdir(parents=True)
        shutil.copyfile(binary, target)
        target.chmod(0o755)
        errors = verify(staged, require_binary=True)
        if errors:
            raise SystemExit("invalid assembled plugin: " + "; ".join(errors))
        doctor = subprocess.run(
            [str(target), "doctor", str(staged)], text=True, capture_output=True, check=False
        )
        if doctor.returncode != 0 or '"ready": true' not in doctor.stdout.lower():
            raise SystemExit(f"tendboat doctor rejected staged plugin: {doctor.stdout}{doctor.stderr}")
        deterministic_archive(staged, args.output.resolve(), f"tendboat-agent-plugin-{lock['plugin_version']}")
    print(f"archive={args.output} sha256={sha256(args.output.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
