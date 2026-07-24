# Record Protocol

Use this reference when connecting the bundled MV3 extension to a backend.

## Optional Endpoint

The extension can POST a record after local download:

`POST /api/v1/materials/download-records`

This endpoint is optional. Local browser downloads can succeed even when this request fails.

## Payload Shape

```json
{
  "url": "https://v26-web.douyinvod.com/path/video.mp4",
  "sourcePageUrl": "https://www.douyin.com/video/7476431505389145396",
  "platform": "douyin",
  "downloadId": "123",
  "downloadedAt": "2026-05-27T10:00:00.000Z",
  "name": "7476431505389145396.mp4",
  "projectId": "optional-project-id",
  "tags": ["browser-collector", "browser-downloaded", "aweme:7476431505389145396"]
}
```

## Expected Backend Behavior

- Accept bearer auth when available.
- Keep records even if no material is created yet.
- Treat `sourcePageUrl` as the canonical page context for Referer and later re-ingest.
- Detect platform from either page URL or CDN URL when `platform` is omitted.
- Derive Douyin filenames from `modal_id`, `gid`, or `/video/<gid>`.

## CDN Capture Notes

The extension captures only the active tab and only `video/mp4` responses with `content-range` or `content-length`. It avoids self-host requests and skips stale Douyin streams when the current page GID differs from the response document GID.

