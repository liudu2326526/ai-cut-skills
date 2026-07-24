import { clearTab, dropTab } from "./video-store.js";

let activeTabId = null;
let activeTabUrl = "";  // capture 同步用，必须实时跟随当前 tab 的 URL

// 同步：webRequest 热路径专用，只读缓存
export function getCachedActiveTabId() {
  return activeTabId;
}

export function getCachedActiveTabUrl() {
  return activeTabUrl;
}

// async：service worker 启动时调一次预热
export async function warmupActiveTabId() {
  if (activeTabId != null) return activeTabId;
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (tab?.id != null) {
      activeTabId = tab.id;
      activeTabUrl = tab.url || "";
    }
  } catch (err) {
    console.warn("[tab-tracker] warmup failed", err);
  }
  return activeTabId;
}

function broadcast(type, payload) {
  // sidePanel 关闭时 sendMessage 会失败，吞掉即可
  chrome.runtime.sendMessage({ type, ...payload }).catch(() => {});
}

export function initTabTracker() {
  chrome.tabs.onActivated.addListener(async ({ tabId }) => {
    activeTabId = tabId;
    try {
      const tab = await chrome.tabs.get(tabId);
      activeTabUrl = tab?.url || "";
      broadcast("ACTIVE_TAB_CHANGED", {
        tabId,
        url: activeTabUrl,
        title: tab?.title || "",
      });
    } catch (err) {
      activeTabUrl = "";
      broadcast("ACTIVE_TAB_CHANGED", { tabId, url: "", title: "" });
    }
  });

  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    // URL 变更 = 完整页面导航；SPA pushState 由 webNavigation 单独处理
    if (changeInfo.url) {
      console.log("[tab-tracker] tabs.onUpdated url change:", changeInfo.url);
      if (tabId === activeTabId) activeTabUrl = changeInfo.url || tab?.url || "";
      clearTab(tabId);
      broadcast("TAB_VIDEOS_CLEARED", {
        tabId,
        url: changeInfo.url || tab?.url || "",
        title: tab?.title || "",
      });
    }
  });

  // 抖音用 history.pushState 在不同 modal_id 之间切换，tabs.onUpdated 不一定触发
  // 必须用 webNavigation.onHistoryStateUpdated 兜底
  if (chrome.webNavigation?.onHistoryStateUpdated) {
    chrome.webNavigation.onHistoryStateUpdated.addListener((details) => {
      if (details.frameId !== 0) return;  // 只关心主 frame
      console.log("[tab-tracker] webNavigation.onHistoryStateUpdated:", details.url);
      if (details.tabId === activeTabId) activeTabUrl = details.url || "";
      clearTab(details.tabId);
      broadcast("TAB_VIDEOS_CLEARED", {
        tabId: details.tabId,
        url: details.url || "",
        title: "",
      });
    });
  }

  chrome.tabs.onRemoved.addListener((tabId) => {
    if (tabId === activeTabId) {
      activeTabId = null;
      activeTabUrl = "";
    }
    dropTab(tabId);
  });
}
