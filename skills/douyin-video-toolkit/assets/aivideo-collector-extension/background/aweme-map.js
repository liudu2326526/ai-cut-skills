const awemeByPath = new Map();
const pathsByAweme = new Map();
const metaByAweme = new Map();
const metaByPath = new Map();

function getUrlPath(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
}

export function addAwemeEntries(entries = []) {
  let added = 0;
  for (const entry of entries) {
    const awemeId = String(entry?.awemeId || entry?.aweme_id || "").trim();
    const videoUrl = String(entry?.videoUrl || entry?.video_url || "").trim();
    if (!awemeId || !videoUrl) continue;

    const path = getUrlPath(videoUrl);
    if (!path) continue;

    if (!awemeByPath.has(path)) added += 1;
    awemeByPath.set(path, awemeId);

    const paths = pathsByAweme.get(awemeId) || new Set();
    paths.add(path);
    pathsByAweme.set(awemeId, paths);

    const meta = {
      title: String(entry?.title || "").trim(),
      coverUrl: String(entry?.coverUrl || entry?.cover_url || "").trim(),
    };
    const existingAwemeMeta = metaByAweme.get(awemeId) || {};
    const mergedMeta = {
      title: existingAwemeMeta.title || meta.title,
      coverUrl: existingAwemeMeta.coverUrl || meta.coverUrl,
    };
    metaByAweme.set(awemeId, mergedMeta);
    metaByPath.set(path, mergedMeta);
  }
  return added;
}

export function findAwemeIdForUrl(url) {
  const path = getUrlPath(url);
  return path ? awemeByPath.get(path) || "" : "";
}

export function annotateVideo(video) {
  if (!video) return video;
  const path = getUrlPath(video.url);
  const mapAwemeId = path ? awemeByPath.get(path) || "" : "";

  // 如果 video 已有 awemeId（来自 capture 的 activeGid），优先用它查 meta
  // 不要用 pathname 反查的 mapAwemeId 覆盖——可能是过时的旧映射
  const awemeId = video.awemeId || mapAwemeId;
  const meta = (awemeId ? metaByAweme.get(awemeId) : null) || {};

  // 只有当 meta 对应的 awemeId 跟 video.awemeId 一致时才回填 title/coverUrl
  // 否则可能把别的作品的元数据错误附加上来
  const shouldApplyMeta = awemeId && awemeId === video.awemeId;

  return {
    ...video,
    awemeId: awemeId || video.awemeId,
    title: video.title || (shouldApplyMeta ? meta.title : "") || "",
    coverUrl: video.coverUrl || (shouldApplyMeta ? meta.coverUrl : "") || "",
  };
}

export function annotateVideos(videos = []) {
  return videos.map((video) => annotateVideo(video));
}

export function getAwemeMapStats() {
  return {
    paths: awemeByPath.size,
    awemes: pathsByAweme.size,
    metadata: metaByAweme.size,
  };
}
