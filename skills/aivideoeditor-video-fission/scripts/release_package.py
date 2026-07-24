from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path


def main() -> int:
    args = parse_args()
    zip_path = Path(args.zip_path).resolve()
    if args.source_dir:
        source_dir = Path(args.source_dir).resolve()
        if not source_dir.is_dir():
            raise SystemExit(f"Source directory does not exist: {source_dir}")
        create_zip(source_dir, zip_path)
    if not zip_path.is_file():
        raise SystemExit(f"Zip file does not exist: {zip_path}")

    metadata = build_metadata(zip_path, args.version, args.download_url, args.release_note)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print()
    print(to_env_lines(metadata))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or verify AIVideoEditor material remix tool release metadata.")
    parser.add_argument("--zip-path", required=True, help="Release zip path to create or inspect.")
    parser.add_argument("--source-dir", default="", help="Optional prepared folder to zip.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--download-url", default="")
    parser.add_argument("--release-note", default="Windows local desktop tool package.")
    return parser.parse_args()


def create_zip(source_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_dir():
                continue
            archive.write(path, path.relative_to(source_dir.parent))


def build_metadata(zip_path: Path, version: str, download_url: str, release_note: str) -> dict[str, object]:
    size = zip_path.stat().st_size
    return {
        "version": version,
        "file_name": zip_path.name,
        "file_size": size,
        "file_size_text": human_size(size),
        "sha256": sha256_file(zip_path),
        "download_url": download_url,
        "release_note": release_note,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def to_env_lines(metadata: dict[str, object]) -> str:
    mapping = {
        "MATERIAL_REMIX_TOOL_VERSION": metadata["version"],
        "MATERIAL_REMIX_TOOL_FILE_NAME": metadata["file_name"],
        "MATERIAL_REMIX_TOOL_FILE_SIZE": metadata["file_size"],
        "MATERIAL_REMIX_TOOL_FILE_SIZE_TEXT": metadata["file_size_text"],
        "MATERIAL_REMIX_TOOL_SHA256": metadata["sha256"],
        "MATERIAL_REMIX_TOOL_DOWNLOAD_URL": metadata["download_url"],
        "MATERIAL_REMIX_TOOL_RELEASE_NOTE": metadata["release_note"],
    }
    return "\n".join(f"{key}={escape_env_value(value)}" for key, value in mapping.items())


def escape_env_value(value: object) -> str:
    text = str(value)
    if not text:
        return ""
    if any(ch.isspace() for ch in text) or any(ch in text for ch in "#'\""):
        return json.dumps(text, ensure_ascii=False)
    return text


if __name__ == "__main__":
    raise SystemExit(main())
