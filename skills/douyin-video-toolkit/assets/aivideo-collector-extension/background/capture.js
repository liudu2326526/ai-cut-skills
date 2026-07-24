import { getCachedActiveTabId, getCachedActiveTabUrl } from "./tab-tracker.js";
import { addVideo } from "./video-store.js";
import { findAwemeIdForUrl } from "./aweme-map.js";
import { COLLECTOR_CONFIG } from "../config.js";

// 黑名单 = 精确 hostname；空数组时跳过该过滤。本地开发和线上 API 各自加自己的。
const SELF_HOSTNAMES = new Set(COLLECTOR_CONFIG.selfHostnames || []);
const ATTR_FILTER = { urls: ["http://*/*", "https://*/*"] };
const EXTRA_INFO = ["responseHeaders"];

function normalizeHeaders(headers = []) {
  const out = {};
  for (const h of headers) {
    if (h?.name) out[h.name.toLowerCase()] = h.value || "";
  }
  return out;
}

function parseContentType(value) {
  return (value || "").toLowerCase().split(";")[0].trim();
}

function parseTotalBytes(contentRange) {
  // 形如 "bytes 0-1023/12345678"
  const m = /\/(\d+)$/.exec(contentRange || "");
  return m ? Number(m[1]) : null;
}

function parseContentLength(contentLength) {
  const size = Number(contentLength || 0);
  return Number.isFinite(size) && size > 0 ? size : null;
}

function parseFilename(contentDisposition) {
  if (!contentDisposition) return "";
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
  if (utf8) {
    try { return decodeURIComponent(utf8[1].replace(/"/g, "")); }
    catch { return utf8[1].replace(/"/g, ""); }
  }
  const m = /filename="?([^";]+)"?/i.exec(contentDisposition);
  return m ? m[1] : "";
}

function fallbackNameFromUrl(url) {
  try {
    const name = new URL(url).pathname.split("/").filter(Boolean).pop();
    return name || "";
  } catch { return ""; }
}

function isSelfRequest(url) {
  if (!SELF_HOSTNAMES.size) return false;
  try {
    return SELF_HOSTNAMES.has(new URL(url).hostname);
  } catch {
    return false;
  }
}

function extractDouyinGid(pageUrl) {
  try {
    const u = new URL(pageUrl || "");
    if (!u.hostname.endsWith("douyin.com")) return "";
    return u.searchParams.get("modal_id") || u.searchParams.get("gid") || "";
  } catch { return ""; }
}

function hashText(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function buildStreamId(url, requestId) {
  const base = requestId || url;
  return hashText(base || String(Date.now()));
}

export function initCapture() {
  // 同步回调；不要写 async，否则 MV3 service worker 冷启动会全量漏抓
  chrome.webRequest.onResponseStarted.addListener(
    (details) => {
      // 关卡 ④：自家请求
      if (isSelfRequest(details.url)) return;

      // 关卡 ①：必须当前 active tab（同步读缓存；冷启动期间 null 时直接放弃）
      const activeId = getCachedActiveTabId();
      if (activeId == null || details.tabId !== activeId) return;

      const headers = normalizeHeaders(details.responseHeaders);

      // 关卡 ②：content-type 主类型 video/mp4
      if (parseContentType(headers["content-type"]) !== "video/mp4") return;

      // 关卡 ③：优先使用 Range 响应；部分平台会直接返回完整 200 视频，只带 content-length
      const contentRange = headers["content-range"];
      const contentLength = headers["content-length"];
      if (!contentRange && !contentLength) return;

      // 关卡 ⑤：抖音 SPA stale-stream 过滤
      // 切下一个视频时，旧视频的 stream 还在传，documentUrl 仍是旧 modal_id
      // 如果跟当前 active tab 的 modal_id 对不上，跳过——这是上一个视频的残留
      const activeUrl = getCachedActiveTabUrl();
      const docUrl = details.documentUrl || "";
      const activeGid = extractDouyinGid(activeUrl);
      const docGid = extractDouyinGid(docUrl);
      if (activeGid && docGid && activeGid !== docGid) {
        console.log("[capture] SKIP stale-stream", { activeGid, docGid, url: details.url.slice(0, 80) });
        return;
      }

      const totalBytes = parseTotalBytes(contentRange) || parseContentLength(contentLength);
      console.log("[capture] +video", {
        activeGid: activeGid || "(none)",
        docGid: docGid || "(none)",
        totalBytes,
        url: details.url.slice(0, 80),
        documentUrl: docUrl.slice(0, 80),
      });

      const requestId = headers["request-id"] || headers["x-request-id"] || "";
      addVideo(details.tabId, {
        url: details.url,
        contentType: "video/mp4",
        totalBytes,
        name: parseFilename(headers["content-disposition"]) || fallbackNameFromUrl(details.url),
        requestId,
        streamId: buildStreamId(details.url, requestId),
        // 优先信任页面 URL 的 modal_id（100% 准确），aweme-map 反查可能过时
        awemeId: activeGid || findAwemeIdForUrl(details.url),
        // 优先记 active tab URL（最新最准），documentUrl 兜底
        pageUrl: activeUrl || docUrl,
        documentUrl: docUrl,  // 单独保留供诊断
        capturedAt: new Date().toISOString(),
      });
    },
    ATTR_FILTER,
    EXTRA_INFO
  );
}
