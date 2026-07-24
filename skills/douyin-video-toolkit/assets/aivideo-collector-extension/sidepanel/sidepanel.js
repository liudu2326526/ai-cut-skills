import { resolveAuth, authHeaders } from "./auth.js";
import { COLLECTOR_CONFIG } from "../config.js";
import { probeMp4AudioTrack } from "./mp4-audio-probe.js";
import { buildQualityDurationHint } from "./media-display.js";

const state = {
  activeTabId: null,
  activeTabUrl: "",
  activeTabTitle: "",
  videos: [],
  selected: new Set(),
  auth: { token: "", userId: "" },
  projects: [],
};

const els = {
  apiBase: document.getElementById("apiBase"),
  projectId: document.getElementById("projectId"),
  authStatus: document.getElementById("authStatus"),
  videoList: document.getElementById("videoList"),
  selectAll: document.getElementById("selectAll"),
  download: document.getElementById("download"),
  clear: document.getElementById("clear"),
  refresh: document.getElementById("refresh"),
  status: document.getElementById("status"),
};

const audioProbeByUrl = new Map();

// ---------- 工具 ----------

function setStatus(msg) { els.status.textContent = msg || ""; }

function audioProbeLabel(video) {
  const probe = audioProbeByUrl.get(video.url);
  if (!probe || probe.status === "checking") return " · 音频检测中";
  if (probe.status === "has-audio") return " · 有音频";
  if (probe.status === "no-audio") return " · ⚠ 无音频";
  return " · ⚠ 音频未确认";
}

function scheduleAudioProbe(video) {
  if (!video?.url || audioProbeByUrl.has(video.url)) return;
  audioProbeByUrl.set(video.url, { status: "checking" });
  probeMp4AudioTrack(video.url)
    .then((hasAudio) => {
      audioProbeByUrl.set(video.url, {
        status: hasAudio === true ? "has-audio" : hasAudio === false ? "no-audio" : "unknown",
      });
    })
    .catch((err) => {
      console.warn("[audio-probe] failed", { url: video.url, error: err?.message || String(err) });
      audioProbeByUrl.set(video.url, { status: "unknown" });
    })
    .finally(() => {
      if (state.videos.some((item) => item.url === video.url)) render();
    });
}

function safeFilename(name) {
  return (name || "captured-video.mp4")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, " ")
    .trim() || "captured-video.mp4";
}

function extractDouyinGid(pageUrl) {
  try {
    const u = new URL(pageUrl);
    if (!u.hostname.endsWith("douyin.com")) return "";
    return u.searchParams.get("modal_id") || u.searchParams.get("gid") || "";
  } catch { return ""; }
}

function extractXiaohongshuNoteId(pageUrl) {
  try {
    const u = new URL(pageUrl);
    if (!u.hostname.endsWith("xiaohongshu.com")) return "";
    // /explore/<noteId> 或 /discovery/item/<noteId>
    const m = u.pathname.match(/\/(?:explore|discovery\/item)\/([a-f0-9]+)/);
    return m ? m[1] : "";
  } catch { return ""; }
}

function detectPlatform(pageUrl, videoUrl) {
  const text = `${pageUrl || ""} ${videoUrl || ""}`.toLowerCase();
  if (text.includes("douyin.com") || text.includes("douyinvod.com")) return "douyin";
  if (text.includes("xiaohongshu.com") || text.includes("xhslink.com")) return "xiaohongshu";
  if (text.includes("kuaishou.com") || text.includes("gifshow.com")) return "kuaishou";
  if (text.includes("tiktok.com")) return "tiktok";
  return "";
}

function currentAwemeId() {
  const id = extractDouyinGid(state.activeTabUrl);
  return id && /^\d+$/.test(id) ? id : "";
}

function appendOrdinal(name, ordinal) {
  if (!ordinal) return name;
  const m = /^(.*?)(\.[^.]+)?$/.exec(name);
  const base = m[1] || name;
  const ext = m[2] || ".mp4";
  return `${base}-${ordinal + 1}${ext}`;
}

function suggestedName(video, index = 0, total = 1) {
  const gid = extractDouyinGid(state.activeTabUrl);
  // 抖音
  if (gid && /^\d+$/.test(gid)) {
    if (video.awemeId && video.awemeId !== gid && video.streamId) {
      return safeFilename(`${video.awemeId}.mp4`);
    }
    return safeFilename(`${gid}.mp4`);
  }
  // 小红书
  const noteId = extractXiaohongshuNoteId(state.activeTabUrl);
  if (noteId) {
    return safeFilename(`${noteId}.mp4`);
  }
  // 非抖音/小红书 fallback
  let name;
  const base = (video.name || "").replace(/\.\w+$/, "");
  if (video.name && !/^[0-9a-f]{16,}$/i.test(base)) {
    name = video.name;
  } else {
    try {
      const fromUrl = new URL(video.url).pathname.split("/").filter(Boolean).pop();
      name = fromUrl || `captured-${Date.now()}.mp4`;
    } catch {
      name = `captured-${Date.now()}.mp4`;
    }
  }
  return safeFilename(appendOrdinal(name, index));
}

function displayTitle(video, index = 0, total = 1) {
  return suggestedName(video, index, total);
}

function apiBase() {
  return (els.apiBase.value || "").trim().replace(/\/$/, "");
}

// chrome.downloads.download 返回 ID 时下载还没完成。
// 等待真完成或中断，并校验下来的是不是真视频（CDN 返回 HTML 错误页时 mime 不是 video/*）。
function waitForDownload(downloadId, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      settled = true;
      chrome.downloads.onChanged.removeListener(handler);
      clearTimeout(timer);
    };
    const handler = async (delta) => {
      if (delta.id !== downloadId) return;
      const newState = delta.state?.current;
      if (newState === "complete") {
        cleanup();
        try {
          const [item] = await chrome.downloads.search({ id: downloadId });
          console.log("[download] completed", { id: downloadId, mime: item?.mime, fileSize: item?.fileSize });
          if (item?.mime && !item.mime.startsWith("video/") && !item.mime.startsWith("application/octet-stream")) {
            chrome.downloads.removeFile(downloadId).catch(() => {});
            chrome.downloads.erase({ id: downloadId }).catch(() => {});
            reject(new Error(`本地保存得到的不是视频 (${item.mime})`));
          } else {
            resolve(item);
          }
        } catch (err) {
          resolve();
        }
      } else if (newState === "interrupted") {
        cleanup();
        reject(new Error(delta.error?.current || "下载中断"));
      }
    };
    const timer = setTimeout(() => {
      if (!settled) {
        cleanup();
        reject(new Error("下载超时（120s）"));
      }
    }, timeoutMs);
    chrome.downloads.onChanged.addListener(handler);
  });
}

// 下载主路径：扩展 fetch 拿 blob → blob URL 喂给 chrome.downloads.download
// 原因：chrome.downloads.download 走的不是常规网络栈，DNR 可能不应用 Referer。
// 而扩展 fetch 一定走常规栈，DNR 修改 Referer 必生效，能突破 CDN 的 Referer 校验。
async function downloadVideoViaBlob(video, filename) {
  // 1. 扩展上下文 fetch（DNR 会在网络层注入 Referer = https://www.douyin.com/）
  //    必须带 Range: bytes=0- 否则 CDN 可能只返回首段（几百 KB）
  const resp = await fetch(video.url, {
    method: "GET",
    credentials: "omit",
    cache: "no-cache",
    headers: { "Range": "bytes=0-" },
  });
  if (!resp.ok) {
    throw new Error(`CDN 拒绝：HTTP ${resp.status} ${resp.statusText}`);
  }
  const contentType = resp.headers.get("content-type") || "";
  if (contentType && !contentType.toLowerCase().startsWith("video/") && !contentType.startsWith("application/octet-stream")) {
    throw new Error(`CDN 返回 ${contentType}（不是视频）`);
  }

  // 2. 拿 blob 并校验大小
  const blob = await resp.blob();
  if (video.totalBytes && blob.size < video.totalBytes * 0.5) {
    console.warn("[download] blob size mismatch", { expected: video.totalBytes, got: blob.size });
    throw new Error(`下载不完整：期望 ${(video.totalBytes / 1024 / 1024).toFixed(1)} MB，实际只拿到 ${(blob.size / 1024 / 1024).toFixed(1)} MB`);
  }

  // 3. 触发本地下载
  const blobUrl = URL.createObjectURL(blob);
  try {
    const downloadId = await chrome.downloads.download({
      url: blobUrl,
      filename,
      saveAs: false,
      conflictAction: "uniquify",
    });
    if (!downloadId) throw new Error("downloads.download 未返回 ID");
    await waitForDownload(downloadId);
    return downloadId;
  } finally {
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
  }
}

function formatAge(ms) {
  const sec = Math.max(0, Math.round(ms / 1000));
  if (sec < 60) return `${sec}s 前`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m 前`;
  return `${Math.round(min / 60)}h 前`;
}

function sortVideos(videos) {
  return [...videos].sort((a, b) => {
    // 优先 hitCount：当前播放的视频会被 range 多次，累计高
    const hitDiff = Number(b.hitCount || 0) - Number(a.hitCount || 0);
    if (hitDiff !== 0) return hitDiff;
    const sizeDiff = Number(b.totalBytes || 0) - Number(a.totalBytes || 0);
    if (sizeDiff !== 0) return sizeDiff;
    return new Date(b.capturedAt).getTime() - new Date(a.capturedAt).getTime();
  });
}

// 返回当前应该展示的视频列表
// 优先级：
// 1. 非抖音页：全部显示
// 2. aweme-map 命中 → 只展示命中条
// 3. 按 pageUrl modal_id 匹配 → 展示所有同页捕获（用户用预览缩略图自己挑）
// 4. 都没匹配 → 全部展示
function visibleVideos() {
  const sorted = sortVideos(state.videos);
  const awemeId = currentAwemeId();

  if (!awemeId) return sorted;

  const awemeMatched = sorted.filter((v) => String(v.awemeId || "") === awemeId);
  if (awemeMatched.length > 0) return awemeMatched;

  const pageMatched = sorted.filter((v) => extractDouyinGid(v.pageUrl || "") === awemeId);
  if (pageMatched.length > 0) return pageMatched;

  return sorted;
}

// ---------- 渲染 ----------

function render() {
  els.videoList.replaceChildren();
  const videos = visibleVideos();
  if (videos.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "未捕获到视频，请刷新当前页并播放一次。";
    els.videoList.appendChild(empty);
    els.download.disabled = true;
    return;
  }

  const awemeId = currentAwemeId();
  const hasAwemeMatched = awemeId && state.videos.some((video) => String(video.awemeId || "") === awemeId);
  const hasPageMatched = awemeId && !hasAwemeMatched && state.videos.some((v) => extractDouyinGid(v.pageUrl || "") === awemeId);

  // 注意：不再做"自动勾选最大那条"——多候选场景下经常错。让用户用预览自己挑。
  if (videos.length > 1 && awemeId && !hasAwemeMatched) {
    const hint = document.createElement("div");
    hint.className = "list-hint";
    hint.textContent = `💡 当前页作品 ID：${awemeId}。多候选按大小排序，最大的通常是最高画质。如需更高清晰度，先在抖音播放器里切换到「高清 1080P」再刷新。`;
    els.videoList.appendChild(hint);
  }

  videos.forEach((video, index) => {
    scheduleAudioProbe(video);

    const row = document.createElement("label");
    row.className = "row";
    if (hasAwemeMatched && String(video.awemeId || "") === awemeId) row.classList.add("is-current-aweme");

    // 标记陈旧候选（>90s 抖音 CDN URL 通常已开始过期）
    const ageMs = Date.now() - new Date(video.capturedAt).getTime();
    const isStale = ageMs > 90 * 1000;
    if (isStale) row.classList.add("is-stale");

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = state.selected.has(video.url);
    cb.addEventListener("change", () => {
      if (cb.checked) state.selected.add(video.url);
      else state.selected.delete(video.url);
      els.download.disabled = state.selected.size === 0;
    });

    // 视频预览：hover 时播放，让用户一眼分辨当前视频
    const preview = document.createElement("video");
    preview.className = "preview";
    preview.src = video.url;
    preview.muted = true;
    preview.preload = "metadata";
    preview.playsInline = true;
    preview.addEventListener("mouseenter", () => preview.play().catch(() => {}));
    preview.addEventListener("mouseleave", () => {
      preview.pause();
      preview.currentTime = 0;
    });
    preview.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (preview.paused) preview.play().catch(() => {});
      else preview.pause();
    });

    const info = document.createElement("div");
    info.className = "info";

    const title = document.createElement("div");
    title.className = "title";
    title.textContent = displayTitle(video, index, videos.length);
    info.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "meta";
    const size = video.totalBytes ? `${(video.totalBytes / 1024 / 1024).toFixed(1)} MB` : "未知大小";
    const aweme = video.awemeId ? `作品 ${video.awemeId}` : "作品未识别";
    let mark = "";
    if (hasAwemeMatched && String(video.awemeId || "") === awemeId) mark = " · 匹配作品";
    else if (hasPageMatched && extractDouyinGid(video.pageUrl || "") === awemeId) mark = " · 同页捕获";
    const ageStr = formatAge(ageMs);
    const hitStr = video.hitCount > 1 ? ` · 命中×${video.hitCount}` : "";
    const staleHint = isStale ? " · ⚠ URL 可能已过期" : "";

    const buildMetaText = (qualityHint = buildQualityDurationHint({ totalBytes: video.totalBytes })) =>
      `${size} · ${aweme} · ${ageStr}${hitStr}${qualityHint}${mark}${staleHint}${audioProbeLabel(video)}`;

    meta.textContent = buildMetaText();
    info.appendChild(meta);

    // preview 元数据加载完成后重渲染（拿到 duration 才能算码率）
    preview.addEventListener("loadedmetadata", () => {
      const qualityHint = buildQualityDurationHint({
        totalBytes: video.totalBytes,
        durationSeconds: preview.duration,
      });
      meta.textContent = buildMetaText(qualityHint);
    });

    // Fallback：在 douyin tab 内 window.open（带 douyin Referer），浏览器原生处理，右键另存
    const openBtn = document.createElement("button");
    openBtn.className = "open-tab-btn";
    openBtn.textContent = "新标签打开 ↗";
    openBtn.title = "在新标签打开 URL → 视频会原生播放 → 右键视频 → 视频另存为";
    openBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        if (state.activeTabId != null) {
          await chrome.scripting.executeScript({
            target: { tabId: state.activeTabId },
            func: (url) => window.open(url, "_blank"),
            args: [video.url],
          });
        } else {
          await chrome.tabs.create({ url: video.url, active: true });
        }
      } catch (err) {
        setStatus(`打开失败：${err.message}`);
      }
    });
    info.appendChild(openBtn);

    const copyBtn = document.createElement("button");
    copyBtn.className = "open-tab-btn";
    copyBtn.textContent = "复制 URL";
    copyBtn.title = "复制视频 URL 到剪贴板，可粘贴到 yt-dlp / IDM / 浏览器地址栏";
    copyBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(video.url);
        setStatus("URL 已复制到剪贴板");
      } catch (err) {
        setStatus(`复制失败：${err.message}`);
      }
    });
    info.appendChild(copyBtn);

    row.appendChild(cb);
    row.appendChild(preview);
    row.appendChild(info);
    els.videoList.appendChild(row);
  });

  const visibleUrls = new Set(videos.map((video) => video.url));
  state.selected = new Set([...state.selected].filter((url) => visibleUrls.has(url)));
  els.download.disabled = state.selected.size === 0;
}

// ---------- 数据获取 ----------

async function getActiveTab() {
  const resp = await chrome.runtime.sendMessage({ type: "GET_ACTIVE_TAB" });
  state.activeTabId = resp?.tabId ?? null;
  state.activeTabUrl = resp?.url ?? "";
  state.activeTabTitle = resp?.title ?? "";
}

async function refreshVideos() {
  // 每次都重新拉 active tab 信息，SPA 切换后 URL/title 会变
  await getActiveTab();
  if (state.activeTabId == null) {
    state.videos = [];
    render();
    return;
  }
  const resp = await chrome.runtime.sendMessage({
    type: "GET_CAPTURED_VIDEOS",
    tabId: state.activeTabId,
  });
  state.videos = resp?.videos || [];
  // 保留之前的勾选状态（按 URL）
  state.selected = new Set([...state.selected].filter((url) =>
    visibleVideos().some((v) => v.url === url)
  ));
  render();
}

// ---------- 后端 API ----------

async function fetchCurrentUser() {
  const r = await fetch(`${apiBase()}/user/me`, { headers: authHeaders(state.auth) });
  const p = await r.json();
  if (!r.ok || p.code !== 0) throw new Error(p.detail || p.message || "读取登录用户失败");
  return p.data;
}

async function refreshProjects() {
  try {
    const user = await fetchCurrentUser();
    state.auth.userId = user.userId || user.id || state.auth.userId;
    const q = new URLSearchParams({ userId: state.auth.userId, page: "1", pageSize: "100" });
    const r = await fetch(`${apiBase()}/projects?${q}`, { headers: authHeaders(state.auth) });
    const p = await r.json();
    if (!r.ok || p.code !== 0) throw new Error(p.detail || p.message || "读取项目失败");
    state.projects = p.data?.items || [];
    renderProjects();
  } catch (err) {
    setStatus(err.message);
  }
}

function renderProjects(selected = "") {
  els.projectId.replaceChildren();
  if (!state.projects.length) {
    els.projectId.appendChild(new Option("当前用户暂无项目", ""));
    return;
  }
  for (const p of state.projects) {
    els.projectId.appendChild(new Option(p.name || p.id, p.id));
  }
  if (selected && state.projects.some((p) => p.id === selected)) {
    els.projectId.value = selected;
  }
}

// ---------- 下载 ----------

async function downloadSelected() {
  const selected = visibleVideos().filter((v) => state.selected.has(v.url));
  if (!selected.length) return setStatus("请选择要下载的视频");

  els.download.disabled = true;
  setStatus(`正在下载 ${selected.length} 条（请保持本面板打开）…`);

  // 用 visibleVideos().length 决定是否多候选模式（影响文件名规则）
  const visible = visibleVideos();
  const totalVisible = visible.length;

  const results = await Promise.allSettled(
    selected.map(async (video, ordinal) => {
      const filename = suggestedName(video, ordinal, totalVisible);

      // 1. 通过 blob 路线下载（fetch 走标准网络栈，DNR 注入 Referer 必生效）
      let downloadId;
      try {
        downloadId = await downloadVideoViaBlob(video, filename);
      } catch (err) {
        throw { stage: "download", video, message: err.message || String(err) };
      }

      // 2. 后端记录。title/coverUrl 不在这里兜底抓取，避免 SPA 滑动场景下写入错视频元数据。
      try {
        const r = await fetch(`${apiBase()}/materials/download-records`, {
          method: "POST",
          headers: { "content-type": "application/json", ...authHeaders(state.auth) },
          body: JSON.stringify({
            url: video.url,
            sourcePageUrl: state.activeTabUrl || video.pageUrl,
            platform: detectPlatform(state.activeTabUrl || video.pageUrl, video.url),
            downloadId: String(downloadId),
            downloadedAt: new Date().toISOString(),
            name: filename,
            projectId: els.projectId.value || null,
            tags: ["browser-collector", "browser-downloaded", video.awemeId ? `aweme:${video.awemeId}` : "aweme:unknown"],
          }),
        });
        const p = await r.json().catch(() => ({}));
        if (!r.ok || p.code !== 0) {
          throw new Error(p.detail || p.message || `HTTP ${r.status}`);
        }
        return { video, downloadId, recordId: p.data?.id };
      } catch (err) {
        throw { stage: "record", video, downloadId, message: err.message || String(err) };
      }
    })
  );

  // 区分两类失败
  const succeeded = results.filter((r) => r.status === "fulfilled");
  const downloadFailed = results.filter((r) => r.status === "rejected" && r.reason?.stage === "download");
  const recordFailed = results.filter((r) => r.status === "rejected" && r.reason?.stage === "record");

  const parts = [];
  if (succeeded.length) parts.push(`下载并记录 ${succeeded.length} 条`);
  if (recordFailed.length) {
    const firstErr = recordFailed[0]?.reason?.message || "未知错误";
    parts.push(`${recordFailed.length} 条已下载但记录失败：${firstErr}`);
  }
  if (downloadFailed.length) {
    const firstErr = downloadFailed[0]?.reason?.message || "未知错误";
    parts.push(`${downloadFailed.length} 条下载失败：${firstErr}`);
  }
  setStatus(parts.join("；") || "无操作");

  recordFailed.forEach((r) => console.warn("[record] failed", r.reason));
  downloadFailed.forEach((r) => console.warn("[download] failed", r.reason));

  els.download.disabled = state.selected.size === 0;
}

// ---------- 事件接入 ----------

chrome.runtime.onMessage.addListener((msg) => {
  if (!msg?.type) return;
  if (msg.type === "CAPTURED_VIDEO_ADDED" && msg.tabId === state.activeTabId) {
    if (!state.videos.some((v) => v.url === msg.video.url)) {
      state.videos.push(msg.video);
      render();
    }
  } else if (msg.type === "TAB_VIDEOS_CLEARED" && msg.tabId === state.activeTabId) {
    state.videos = [];
    state.selected.clear();
    // 同步新 URL，避免下一次 suggestedName 仍用旧 modal_id
    if (msg.url) state.activeTabUrl = msg.url;
    if (msg.title) state.activeTabTitle = msg.title;
    render();
  } else if (msg.type === "DOUYIN_AWEME_MAP_UPDATED") {
    refreshVideos().catch((err) => setStatus(err.message));
  } else if (msg.type === "ACTIVE_TAB_CHANGED") {
    state.activeTabId = msg.tabId;
    state.activeTabUrl = msg.url;
    state.activeTabTitle = msg.title || "";
    state.selected.clear();
    refreshVideos().catch((err) => setStatus(err.message));
  }
});

els.refresh.addEventListener("click", () => refreshVideos().catch((e) => setStatus(e.message)));

els.clear.addEventListener("click", async () => {
  if (state.activeTabId != null) {
    await chrome.runtime.sendMessage({ type: "CLEAR_CAPTURED_VIDEOS", tabId: state.activeTabId });
  }
  state.videos = [];
  state.selected.clear();
  render();
});

els.selectAll.addEventListener("click", () => {
  const all = visibleVideos().map((v) => v.url);
  const shouldSelectAll = !all.every((u) => state.selected.has(u));
  state.selected = shouldSelectAll ? new Set(all) : new Set();
  render();
});

els.download.addEventListener("click", () => downloadSelected().catch((e) => setStatus(e.message)));

// 设置项变更持久化（apiBase / projectId）
for (const el of [els.apiBase, els.projectId]) {
  el.addEventListener("change", () => {
    chrome.storage.sync.set({ apiBase: els.apiBase.value, projectId: els.projectId.value });
  });
}

// ---------- 启动 ----------

(async function bootstrap() {
  const saved = await chrome.storage.sync.get({
    apiBase: COLLECTOR_CONFIG.defaultApiBase || "http://127.0.0.1:6677/api/v1",
    projectId: "",
  });
  els.apiBase.value = saved.apiBase;

  state.auth = await resolveAuth();
  if (state.auth.token) {
    // 验证 token 是否真的对后端有效
    try {
      await fetchCurrentUser();
      const display = state.auth.username || state.auth.userId || "";
      els.authStatus.textContent = `✅ 已登录：${display}`;
      els.authStatus.className = "auth-status ok";
      els.authStatus.title = `来源：${state.auth.sourceUrl || "未知"}`;
      await refreshProjects();
      if (saved.projectId) renderProjects(saved.projectId);
    } catch (err) {
      // token 无效或对应用户不存在
      els.authStatus.textContent = `⚠️ Token 无效：${err.message}（来源：${state.auth.sourceUrl || "未知"}）`;
      els.authStatus.className = "auth-status missing";
      console.warn("[auth] token invalid", { sourceUrl: state.auth.sourceUrl, userId: state.auth.userId, error: err.message });
      state.auth = { token: "", userId: "", sourceUrl: "" };
    }
  } else {
    els.authStatus.textContent = "未识别，请先打开并登录智剪";
    els.authStatus.className = "auth-status missing";
  }

  await refreshVideos();
})();
