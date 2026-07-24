const videosByTab = new Map();  // tabId -> CapturedVideo[]

function updateBadge(tabId) {
  const count = (videosByTab.get(tabId) || []).length;
  chrome.action.setBadgeText({ tabId, text: count ? String(count) : "" }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" }).catch(() => {});
}

function broadcast(type, payload) {
  chrome.runtime.sendMessage({ type, ...payload }).catch(() => {});
}

export function addVideo(tabId, video) {
  const list = videosByTab.get(tabId) || [];
  const existing = list.find((v) => v.url === video.url);

  if (existing) {
    // 同 URL 已存在：累加命中次数（webRequest 每次 range 都算一次），更新最新看到时间
    existing.hitCount = (existing.hitCount || 1) + 1;
    existing.lastSeenAt = new Date().toISOString();
    if (video.totalBytes && (!existing.totalBytes || video.totalBytes > existing.totalBytes)) {
      existing.totalBytes = video.totalBytes;
    }
    return;
  }

  video.hitCount = 1;
  video.lastSeenAt = video.capturedAt;
  list.push(video);
  videosByTab.set(tabId, list);
  updateBadge(tabId);
  broadcast("CAPTURED_VIDEO_ADDED", { tabId, video });
}

export function getVideos(tabId) {
  return videosByTab.get(tabId) || [];
}

export function clearTab(tabId) {
  videosByTab.set(tabId, []);
  updateBadge(tabId);
}

export function dropTab(tabId) {
  videosByTab.delete(tabId);
  // tab 关闭后角标自动消失，无需 setBadgeText
}
