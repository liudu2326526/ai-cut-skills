(function () {
  const TAG = "[douyin-main]";
  // 同一页面避免重复装载（SPA pushState 可能让脚本被多次评估）
  if (window.__aivideoDouyinInterceptorInstalled__) return;
  window.__aivideoDouyinInterceptorInstalled__ = true;
  console.log(TAG, "installed on", location.href);

  const DETAIL_PATTERNS = [
    "/aweme/v1/web/aweme/detail/",
    "/aweme/v1/web/multi/aweme/detail/",
    "/aweme/v1/web/general/search/single/",
    "/aweme/v1/web/aweme/post/",
    "/aweme/v1/web/aweme/related/",
    "/aweme/v1/web/aweme/favorite/",
    "/aweme/v1/web/mix/aweme/",
    "/aweme/v1/web/comment/list/",
    "/aweme/v1/web/tab/feed/",
    "/aweme/v1/web/follow/feed/",
    "/aweme/v1/web/module/feed/",
    "/aweme/v1/web/hot/search/list/",
  ];

  function shouldIntercept(url) {
    return DETAIL_PATTERNS.some((pattern) => String(url || "").includes(pattern));
  }

  function firstUrl(value) {
    if (!value) return "";
    if (typeof value === "string" && value.startsWith("http")) return value;
    if (Array.isArray(value)) {
      return value.find((item) => typeof item === "string" && item.startsWith("http")) || "";
    }
    if (typeof value === "object") {
      return firstUrl(value.url_list || value.urlList || value.url || value.uri);
    }
    return "";
  }

  function pickTitle(node) {
    return String(
      node?.desc ||
      node?.item_title ||
      node?.caption ||
      node?.share_info?.share_title ||
      ""
    ).trim();
  }

  function pickCover(video) {
    if (!video || typeof video !== "object") return "";
    return (
      firstUrl(video.origin_cover) ||
      firstUrl(video.cover) ||
      firstUrl(video.dynamic_cover) ||
      firstUrl(video.animated_cover)
    );
  }

  function appendUrl(entries, awemeId, value, meta = {}) {
    if (!awemeId || typeof value !== "string" || !value.startsWith("http")) return;
    try {
      new URL(value);
      entries.push({ awemeId: String(awemeId), videoUrl: value, ...meta });
    } catch {}
  }

  function appendPlayAddr(entries, awemeId, playAddr, meta = {}) {
    if (!playAddr || typeof playAddr !== "object") return;
    const urls = playAddr.url_list || playAddr.urlList || [];
    if (Array.isArray(urls)) {
      for (const url of urls) appendUrl(entries, awemeId, url, meta);
    }
    appendUrl(entries, awemeId, playAddr.url, meta);
  }

  function appendVideo(entries, awemeId, video, meta = {}) {
    if (!video || typeof video !== "object") return;
    const videoMeta = { ...meta, coverUrl: meta.coverUrl || pickCover(video) };
    appendPlayAddr(entries, awemeId, video.play_addr, videoMeta);
    appendPlayAddr(entries, awemeId, video.play_addr_h264, videoMeta);
    appendPlayAddr(entries, awemeId, video.download_addr, videoMeta);
    if (Array.isArray(video.bit_rate)) {
      for (const item of video.bit_rate) appendPlayAddr(entries, awemeId, item?.play_addr, videoMeta);
    }
  }

  function collectAwemes(node, entries, seen = new WeakSet()) {
    if (!node || typeof node !== "object") return;
    if (seen.has(node)) return;
    seen.add(node);

    const awemeId = node.aweme_id || node.awemeId || node.item_id || node.itemId;
    if (awemeId && node.video) {
      appendVideo(entries, awemeId, node.video, {
        title: pickTitle(node),
      });
    }

    for (const value of Object.values(node)) {
      if (value && typeof value === "object") collectAwemes(value, entries, seen);
    }
  }

  function extractAndReport(url, responseText) {
    if (!responseText) return;
    let json;
    try {
      json = JSON.parse(responseText);
    } catch {
      console.warn(TAG, "JSON parse failed for", url);
      return;
    }

    const entries = [];
    collectAwemes(json, entries);
    if (!entries.length) {
      console.log(TAG, "no aweme found in", url);
      return;
    }

    const deduped = [];
    const seen = new Set();
    for (const entry of entries) {
      const key = `${entry.awemeId}|${entry.videoUrl}`;
      if (seen.has(key)) continue;
      seen.add(key);
      deduped.push(entry);
    }

    console.log(TAG, `extracted ${deduped.length} mappings from`, url);
    window.postMessage(
      { __aivideo_douyin_aweme_map_report__: true, entries: deduped },
      location.origin
    );
  }

  function maybeExtractFromNetwork(url, responseText) {
    if (!shouldIntercept(url)) return;
    extractAndReport(url, responseText);
  }

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input?.url || String(input);
    const promise = origFetch.apply(this, arguments);
    if (shouldIntercept(url)) {
      promise
        .then((resp) => resp.clone().text().then((text) => maybeExtractFromNetwork(url, text)))
        .catch(() => {});
    }
    return promise;
  };

  const xhrOpen = XMLHttpRequest.prototype.open;
  const xhrSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url) {
    if (typeof url === "string" && shouldIntercept(url)) {
      this.__aivideoDouyinAwemeUrl = url;
    }
    return xhrOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function () {
    if (this.__aivideoDouyinAwemeUrl) {
      const url = this.__aivideoDouyinAwemeUrl;
      this.addEventListener("load", () => {
        try {
          maybeExtractFromNetwork(url, this.responseText || "");
        } catch {}
      });
    }
    return xhrSend.apply(this, arguments);
  };

  // ---------------------------------------------------------------
  // 兜底：扫描页面注入数据。抖音单视频页通常把 aweme 详情塞进
  // <script id="RENDER_DATA"> 或 window._ROUTER_DATA，不发 XHR。
  // 新版抖音 + Next.js 可能塞在 __pace_f / __next_f / 其他 <script> 里。
  // ---------------------------------------------------------------
  function tryReportText(label, text) {
    if (!text || typeof text !== "string" || text.length < 20) return;
    // 直接 JSON.parse
    extractAndReport(label, text);
    // 兜底：text 不是纯 JSON 时，找内嵌的 JSON 片段
    const jsonMatches = text.match(/\{[^{}]*"aweme_id"[^{}]*\}/g);
    if (jsonMatches) {
      for (const fragment of jsonMatches) {
        extractAndReport(label + ":fragment", fragment);
      }
    }
  }

  function scanInjectedData() {
    // 1. RENDER_DATA <script> 标签
    const renderScript = document.getElementById("RENDER_DATA");
    if (renderScript?.textContent) {
      try {
        tryReportText("RENDER_DATA(decoded)", decodeURIComponent(renderScript.textContent));
      } catch {
        tryReportText("RENDER_DATA", renderScript.textContent);
      }
    }

    // 2. window 全局对象
    for (const key of [
      "_ROUTER_DATA", "_SSR_DATA", "__INITIAL_STATE__",
      "__INIT_PROPS__", "_INIT_DATA", "__pace_data__",
      "__SSR_PROPS_DATA__", "__INITIAL_PROPS__",
    ]) {
      try {
        const value = window[key];
        if (value) tryReportText(`window.${key}`, JSON.stringify(value));
      } catch {}
    }

    // 3. 暴力扫描所有非外链 <script>，找含 aweme_id 的
    const scripts = document.querySelectorAll("script:not([src])");
    let scanned = 0;
    for (const s of scripts) {
      const text = s.textContent || "";
      if (text.length < 100) continue;
      if (!text.includes("aweme_id") && !text.includes("play_addr")) continue;
      tryReportText("script-tag", text);
      scanned += 1;
      if (scanned > 30) break;  // 防止某些页面 script 数百个，限流
    }

    // 4. Next.js __next_f / __pace_f
    for (const key of ["__next_f", "__pace_f"]) {
      try {
        const arr = window[key];
        if (Array.isArray(arr)) {
          for (const entry of arr) {
            if (typeof entry === "string") tryReportText(`window.${key}[]`, entry);
            else if (Array.isArray(entry) && typeof entry[1] === "string") tryReportText(`window.${key}[1]`, entry[1]);
          }
        }
      } catch {}
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanInjectedData, { once: true });
  } else {
    scanInjectedData();
  }
  // SPA 切换可能延迟注入；多扫几次兜底
  setTimeout(scanInjectedData, 1500);
  setTimeout(scanInjectedData, 4000);
  setTimeout(scanInjectedData, 8000);
})();
