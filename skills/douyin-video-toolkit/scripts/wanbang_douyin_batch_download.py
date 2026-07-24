from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {message}\n")


@dataclass
class VideoReference:
    source: str
    gid: str
    video_url: str
    keyword: str = ""


@dataclass
class DownloadResult:
    source: str
    gid: str
    video_url: str
    status: str
    keyword: str = ""
    path: str = ""
    file_size: int = 0
    error: str = ""


def build_douyin_video_url(gid: str) -> str:
    return f"https://www.douyin.com/video/{gid}"


def resolve_redirect_url(url: str, timeout: int = 20) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc.endswith("v.douyin.com"):
        return url
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.geturl() or url


def extract_gid_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    for key in ("modal_id", "gid", "video_id", "item_id", "aweme_id"):
        value = (query.get(key) or [""])[0]
        if value and re.match(r"^[A-Za-z0-9_-]+$", value):
            return value

    match = re.search(r"/(?:share/)?video/(\d+)", parsed.path)
    if match:
        return match.group(1)

    resolved = resolve_redirect_url(url)
    if resolved != url:
        return extract_gid_from_url(resolved)
    return ""


def text_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_xlsx_column(path: Path, column: str | None) -> list[str]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("Reading .xlsx input requires openpyxl: pip install openpyxl") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    if column:
        column = column.strip()
        if column.isdigit():
            idx = max(int(column), 1) - 1
        else:
            headers = [str(value or "").strip() for value in rows[0]]
            if column not in headers:
                raise RuntimeError(f"Column not found in {path}: {column}")
            idx = headers.index(column)
            rows = rows[1:]
    else:
        idx = 0

    values: list[str] = []
    for row in rows:
        if idx < len(row):
            value = str(row[idx] or "").strip()
            if value:
                values.append(value)
    return values


def read_csv_column(path: Path, column: str | None) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(2048)
        file.seek(0)
        has_header = csv.Sniffer().has_header(sample) if sample.strip() else False
        if has_header:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []
            selected = column or (fieldnames[0] if fieldnames else "")
            if selected not in fieldnames:
                raise RuntimeError(f"Column not found in {path}: {selected}")
            return [str(row.get(selected) or "").strip() for row in reader if str(row.get(selected) or "").strip()]

        reader = csv.reader(file)
        idx = max(int(column), 1) - 1 if column and column.isdigit() else 0
        values = []
        for row in reader:
            if idx < len(row):
                value = str(row[idx] or "").strip()
                if value:
                    values.append(value)
        return values


def read_values(path: Path, column: str | None) -> list[str]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return read_xlsx_column(path, column)
    if suffix == ".csv":
        return read_csv_column(path, column)
    return text_lines(path)


class WanbangClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str, timeout: int = 90):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.api_secret or not self.base_url:
            raise RuntimeError("Set WANBANG_API_KEY, WANBANG_API_SECRET, and WANBANG_DOUYIN_BASE_URL.")

    def get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        full_params = {
            "key": self.api_key,
            "secret": self.api_secret,
            "cache": "no",
            "result_type": "json",
            **params,
        }
        url = f"{self.base_url.rstrip('/')}/{endpoint.strip('/')}/?{urllib.parse.urlencode(full_params)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
        payload = json.loads(text)
        error_code = str(payload.get("error_code") or "")
        if error_code and error_code != "0000":
            reason = payload.get("reason") or payload.get("error") or "unknown error"
            raise RuntimeError(f"Wanbang {endpoint} failed: {error_code} {reason}")
        return payload

    def search_videos(self, keyword: str, *, page: int, max_videos: int) -> list[VideoReference]:
        payload = self.get_json("item_search_video", {"q": keyword, "page": page})
        items = payload.get("items") or {}
        raw_results = items.get("item") if isinstance(items, dict) else None
        if raw_results is None:
            raw_results = payload.get("item") or []
        if isinstance(raw_results, dict):
            raw_results = [raw_results]

        references: list[VideoReference] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            gid = str(item.get("num_iid") or item.get("item_id") or "").strip()
            if not gid:
                continue
            references.append(
                VideoReference(
                    source=str(item.get("detail_url") or build_douyin_video_url(gid)),
                    gid=gid,
                    video_url=build_douyin_video_url(gid),
                    keyword=keyword,
                )
            )
            if len(references) >= max_videos:
                break
        return references

    def video_download_url(self, gid: str) -> str:
        payload = self.get_json("item_get_video", {"item_id": gid})
        item = payload.get("item") or payload
        video = item.get("video") or {}
        video_url = video.get("url") or video.get("video_url")
        if not video_url:
            raise RuntimeError("Wanbang item_get_video response missing item.video.url")
        return str(video_url)


def download_file(url: str, target_path: Path, *, referer: str = "https://www.douyin.com/") -> int:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Accept": "*/*",
        },
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with urllib.request.urlopen(request, timeout=180) as response:
        with target_path.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                size += len(chunk)
    if size <= 0:
        raise RuntimeError("Downloaded video file is empty")
    return size


def dedupe_references(references: list[VideoReference]) -> list[VideoReference]:
    seen: set[str] = set()
    deduped: list[VideoReference] = []
    for ref in references:
        if ref.gid in seen:
            continue
        seen.add(ref.gid)
        deduped.append(ref)
    return deduped


def write_outputs(results: list[DownloadResult], out_dir: Path) -> None:
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_path = out_dir / "summary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(results[0]).keys()) if results else ["status"])
        writer.writeheader()
        for item in results:
            writer.writerow(asdict(item))


def build_references(args: argparse.Namespace, client: WanbangClient | None) -> list[VideoReference]:
    refs: list[VideoReference] = []
    for url in args.url or []:
        gid = extract_gid_from_url(url)
        if gid:
            refs.append(VideoReference(source=url, gid=gid, video_url=build_douyin_video_url(gid)))

    for path_text in args.urls_file or []:
        for value in read_values(Path(path_text), args.url_column):
            gid = extract_gid_from_url(value)
            if gid:
                refs.append(VideoReference(source=value, gid=gid, video_url=build_douyin_video_url(gid)))

    for gid in args.gid or []:
        text = str(gid).strip()
        if text:
            refs.append(VideoReference(source=text, gid=text, video_url=build_douyin_video_url(text)))

    keywords: list[str] = []
    keywords.extend(args.keyword or [])
    for path_text in args.keywords_file or []:
        keywords.extend(read_values(Path(path_text), args.keyword_column))
    for keyword in [item.strip() for item in keywords if item.strip()]:
        if client is None:
            raise RuntimeError("Wanbang credentials are required for keyword search.")
        refs.extend(client.search_videos(keyword, page=args.page, max_videos=args.max_per_keyword))

    return dedupe_references(refs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch download Douyin videos through Wanbang item_get_video.")
    parser.add_argument("--out-dir", type=Path, default=Path("downloads/douyin-gid-batch"))
    parser.add_argument("--url", action="append", help="Douyin URL. Can be passed multiple times.")
    parser.add_argument("--urls-file", action="append", help="Text, CSV, or XLSX file containing Douyin URLs.")
    parser.add_argument("--url-column", help="CSV/XLSX URL column name or 1-based index.")
    parser.add_argument("--gid", action="append", help="Raw Douyin GID/aweme id. Can be passed multiple times.")
    parser.add_argument("--keyword", action="append", help="Keyword to search through Wanbang item_search_video.")
    parser.add_argument("--keywords-file", action="append", help="Text, CSV, or XLSX file containing keywords.")
    parser.add_argument("--keyword-column", help="CSV/XLSX keyword column name or 1-based index.")
    parser.add_argument("--max-per-keyword", type=int, default=12)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--no-download", action="store_true", help="Only resolve/query references and write summaries.")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse existing <gid>.mp4 files.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to wait between videos.")
    parser.add_argument("--api-key", default=os.getenv("WANBANG_API_KEY", ""))
    parser.add_argument("--api-secret", default=os.getenv("WANBANG_API_SECRET", ""))
    parser.add_argument("--base-url", default=os.getenv("WANBANG_DOUYIN_BASE_URL", ""))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / "run.log"
    append_log(log_path, f"run_start out_dir={args.out_dir.resolve()} no_download={args.no_download} skip_existing={args.skip_existing}")
    has_keyword_inputs = bool(args.keyword or args.keywords_file)
    needs_client = has_keyword_inputs or not args.no_download
    try:
        client = WanbangClient(args.api_key, args.api_secret, args.base_url) if needs_client else None
        refs = build_references(args, client)
    except Exception as exc:
        append_log(log_path, f"prepare_failed error={exc}")
        raise
    if not refs:
        append_log(log_path, "prepare_failed error=No valid Douyin GID references found.")
        raise RuntimeError("No valid Douyin GID references found.")
    append_log(log_path, f"references_ready count={len(refs)}")

    results: list[DownloadResult] = []
    for index, ref in enumerate(refs, start=1):
        target = args.out_dir / f"{ref.gid}.mp4"
        print(f"[{index}/{len(refs)}] {ref.gid}")
        append_log(log_path, f"item_start index={index} gid={ref.gid} source={ref.source}")
        try:
            if args.no_download:
                results.append(DownloadResult(ref.source, ref.gid, ref.video_url, "resolved", keyword=ref.keyword))
            elif args.skip_existing and target.exists() and target.stat().st_size > 0:
                results.append(
                    DownloadResult(
                        ref.source,
                        ref.gid,
                        ref.video_url,
                        "reused",
                        keyword=ref.keyword,
                        path=str(target),
                        file_size=target.stat().st_size,
                    )
                )
            else:
                if client is None:
                    raise RuntimeError("Wanbang credentials are required for downloading.")
                direct_url = client.video_download_url(ref.gid)
                size = download_file(direct_url, target)
                results.append(
                    DownloadResult(
                        ref.source,
                        ref.gid,
                        ref.video_url,
                        "downloaded",
                        keyword=ref.keyword,
                        path=str(target),
                        file_size=size,
                    )
                )
            print(f"  {results[-1].status}")
            append_log(log_path, f"item_{results[-1].status} index={index} gid={ref.gid} path={results[-1].path} size={results[-1].file_size}")
        except Exception as exc:
            results.append(DownloadResult(ref.source, ref.gid, ref.video_url, "failed", keyword=ref.keyword, error=str(exc)))
            print(f"  failed: {exc}")
            append_log(log_path, f"item_failed index={index} gid={ref.gid} error={exc}")
        finally:
            write_outputs(results, args.out_dir)
            append_log(log_path, f"summary_written count={len(results)} summary={(args.out_dir / 'summary.json').resolve()}")
            if args.sleep > 0 and index < len(refs):
                time.sleep(args.sleep)

    append_log(log_path, f"run_end downloaded={sum(1 for item in results if item.status == 'downloaded')} reused={sum(1 for item in results if item.status == 'reused')} failed={sum(1 for item in results if item.status == 'failed')}")
    print((args.out_dir / "summary.json").resolve())


if __name__ == "__main__":
    main()
