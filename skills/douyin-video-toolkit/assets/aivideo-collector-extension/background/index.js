import { initCapture } from "./capture.js";
import { initTabTracker, warmupActiveTabId } from "./tab-tracker.js";
import { initMessaging } from "./messaging.js";
import { initRefererInjector } from "./referer-injector.js";

// 1. sidePanel 行为
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((err) => console.error("[sidePanel] setPanelBehavior failed", err));

chrome.action.onClicked.addListener((tab) => {
  if (tab?.id != null) chrome.sidePanel.open({ tabId: tab.id });
});

// 2. 各模块装配（顺序不能反：tracker 先于 capture）
initTabTracker();
initCapture();
initMessaging();

// 3. 给下载请求注入 Referer（fire-and-forget；CDN 接受请求所必需）
initRefererInjector().catch(() => {});

// 4. 预热 activeTabId（fire-and-forget；capture 走同步 getCachedActiveTabId）
warmupActiveTabId().catch(() => {});
