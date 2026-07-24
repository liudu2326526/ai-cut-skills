import { COLLECTOR_CONFIG } from "../config.js";

const APP_ORIGINS = new Set(COLLECTOR_CONFIG.appOrigins || []);

function isScriptable(url) {
  return /^https?:\/\//i.test(url || "");
}

function isAllowedAppOrigin(url) {
  if (!APP_ORIGINS.size) return true;
  try {
    return APP_ORIGINS.has(new URL(url || "").origin);
  } catch {
    return false;
  }
}

function isAivideoCandidate(result) {
  if (!result?.token || !result?.userId) return false;
  if (!isAllowedAppOrigin(result.href)) return false;
  const text = `${result.href || ""} ${result.title || ""}`.toLowerCase();
  return (
    text.includes("aivideo") ||
    text.includes("智剪") ||
    text.includes("ai视频") ||
    text.includes("ai video") ||
    result.hasAivideoProfile
  );
}

async function readAuthFromTab(tab) {
  if (!tab?.id || !isScriptable(tab.url)) return null;
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const parseJson = (v) => { try { return JSON.parse(v); } catch { return null; } };
        const userInfo = parseJson(localStorage.getItem("userInfo")) || {};
        return {
          href: window.location.href,
          title: document.title,
          token: localStorage.getItem("token") || "",
          userId: localStorage.getItem("userId") || userInfo.userId || userInfo.id || "",
          username: userInfo.username || userInfo.nickname || userInfo.realName || "",
          lastActiveAt: Number(localStorage.getItem("aivideoCollectorLastActiveAt") || 0),
          hasAivideoProfile: Boolean(userInfo.wxUserId || userInfo.realName || userInfo.isActive !== undefined),
        };
      },
    });
    return result || null;
  } catch {
    return null;
  }
}

export async function resolveAuth() {
  const tabs = await chrome.tabs.query({});
  const candidates = [];
  for (const tab of tabs) {
    const r = await readAuthFromTab(tab);
    if (isAivideoCandidate(r)) {
      candidates.push({
        ...r,
        tabActive: Boolean(tab.active),
        tabIndex: Number(tab.index || 0),
      });
    }
  }
  candidates.sort((a, b) => {
    const activeDiff = Number(b.tabActive) - Number(a.tabActive);
    if (activeDiff) return activeDiff;
    const timeDiff = Number(b.lastActiveAt || 0) - Number(a.lastActiveAt || 0);
    if (timeDiff) return timeDiff;
    return Number(b.tabIndex || 0) - Number(a.tabIndex || 0);
  });
  const selected = candidates[0];
  if (selected) {
    return {
      token: selected.token,
      userId: selected.userId,
      username: selected.username,
      sourceUrl: selected.href,
    };
  }
  return { token: "", userId: "", sourceUrl: "" };
}

export function authHeaders(auth) {
  if (!auth?.token) throw new Error("未识别到智剪登录用户，请先打开并登录智剪");
  return { authorization: `Bearer ${auth.token}` };
}
