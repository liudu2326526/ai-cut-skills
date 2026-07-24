from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
EXTENSION_DIR = SKILL_DIR / "assets" / "aivideo-collector-extension"


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def config_js(api_base: str, app_origins: list[str], self_hostnames: list[str]) -> str:
    config = {
        "defaultApiBase": api_base.rstrip("/"),
        "appOrigins": app_origins,
        "selfHostnames": self_hostnames,
    }
    return f"export const COLLECTOR_CONFIG = {json.dumps(config, ensure_ascii=False, indent=2)};\n"


def package_extension(
    output: Path,
    *,
    api_base: str,
    app_origins: list[str],
    self_hostnames: list[str],
) -> Path:
    if not EXTENSION_DIR.exists():
        raise FileNotFoundError(f"Extension asset not found: {EXTENSION_DIR}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(EXTENSION_DIR.rglob("*")):
            if path.is_dir() or path.name == ".DS_Store":
                continue
            rel = path.relative_to(EXTENSION_DIR.parent)
            if path.name == "config.js" and path.parent == EXTENSION_DIR:
                archive.writestr(
                    str(rel).replace("\\", "/"),
                    config_js(api_base, app_origins, self_hostnames),
                )
                continue
            archive.write(path, str(rel).replace("\\", "/"))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the standalone browser video collector extension.")
    parser.add_argument("--output", type=Path, default=Path("aivideo-collector-extension.zip"))
    parser.add_argument("--api-base", default="http://127.0.0.1:6677/api/v1")
    parser.add_argument("--app-origins", default="http://127.0.0.1:5176,http://localhost:5176")
    parser.add_argument("--self-hostnames", default="localhost,127.0.0.1")
    args = parser.parse_args()

    path = package_extension(
        args.output,
        api_base=args.api_base,
        app_origins=parse_csv(args.app_origins),
        self_hostnames=parse_csv(args.self_hostnames),
    )
    print(path.resolve())


if __name__ == "__main__":
    main()
