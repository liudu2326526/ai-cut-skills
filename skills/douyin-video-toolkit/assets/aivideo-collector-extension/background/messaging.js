import { getVideos, clearTab } from "./video-store.js";
import { addAwemeEntries, annotateVideos, getAwemeMapStats } from "./aweme-map.js";

export function initMessaging() {
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg?.type) return false;

    switch (msg.type) {
      case "GET_CAPTURED_VIDEOS": {
        sendResponse({ videos: annotateVideos(getVideos(msg.tabId)) });
        return false;
      }

      case "CLEAR_CAPTURED_VIDEOS": {
        clearTab(msg.tabId);
        sendResponse({ ok: true });
        return false;
      }

      case "GET_ACTIVE_TAB": {
        chrome.tabs.query({ active: true, lastFocusedWindow: true }).then(([tab]) => {
          if (!tab?.id || !/^https?:\/\//i.test(tab.url || "")) {
            sendResponse({ tabId: tab?.id ?? null, url: tab?.url ?? "", title: tab?.title ?? "", coverUrl: "" });
            return;
          }
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const absolutize = (value) => {
                if (!value) return "";
                try { return new URL(value, location.href).href; } catch { return ""; }
              };

              // ---- 标题 ----
              let title = "";
              const isDouyin = location.hostname.endsWith("douyin.com");
              const isXhs = location.hostname.endsWith("xiaohongshu.com");
              if (isDouyin) {
                // 抖音精选/详情/搜索：各种弹窗/页面结构的标题 DOM
                const titleSelectors = [
                  // 精选页 modal 弹窗
                  '.video-info-detail [data-e2e="video-desc"]',
                  '[data-e2e="video-desc"]',
                  '.video-info-detail .title',
                  // 详情页
                  '.detail-desc',
                  '.video-meta-info .title',
                  // 搜索页
                  '.search-result-card .title',
                  // 通用
                  '.immersive-player-switch-modal-mask ~ div [data-e2e="video-desc"]',
                ];
                for (const sel of titleSelectors) {
                  const el = document.querySelector(sel);
                  const text = (el?.innerText || "").replace(/\s+/g, " ").trim();
                  // 过滤掉 UI 碎片：太短（<4字）、含「抖音」「登录」「倍速」等
                  if (text && text.length >= 4 && text.length < 200 &&
                      !/抖音|登录|注册|倍速|清屏|连播|智能|搜索|详情|评论/.test(text)) {
                    title = text;
                    break;
                  }
                }
                // 如果上面都没拿到，尝试从页面里所有 span/p 文本里找最长的非 UI 文本
                if (!title) {
                  const candidates = [];
                  for (const el of document.querySelectorAll(".video-info-detail span, .video-info-detail p")) {
                    const t = (el.innerText || "").replace(/\s+/g, " ").trim();
                    if (t.length >= 6 && t.length < 200 && !/抖音|登录|注册|倍速/.test(t)) {
                      candidates.push(t);
                    }
                  }
                  if (candidates.length) title = candidates.sort((a, b) => b.length - a.length)[0];
                }
              } else if (isXhs) {
                const el = document.querySelector('#detail-title, .note-text, [data-name="note-title"]');
                title = (el?.innerText || "").replace(/\s+/g, " ").trim();
              }
              // 通用 fallback：清理 document.title
              if (!title) {
                title = (document.title || "")
                  .replace(/\s*-\s*抖音.*$/i, "")
                  .replace(/\s*-\s*小红书.*$/i, "")
                  .replace(/\s*-\s*Douyin.*$/i, "")
                  .replace(/\s*-\s*Google Chrome.*$/i, "")
                  .trim();
              }

              // ---- 封面 ----
              let coverUrl = "";
              if (isDouyin) {
                // 优先找当前播放 <video> 的 poster 属性
                const videos = [...document.querySelectorAll("video")];
                const playing = videos.find((v) => !v.paused && !v.ended);
                const visible = videos.find((v) => {
                  const rect = v.getBoundingClientRect();
                  return rect.width > 100 && rect.height > 100 && rect.top < window.innerHeight && rect.bottom > 0;
                });
                const bestVideo = playing || visible || videos[0];
                if (bestVideo?.poster) {
                  coverUrl = absolutize(bestVideo.poster);
                }
                // 其次找 xg-poster img
                if (!coverUrl) {
                  const posterImg = document.querySelector("xg-poster img, .xgplayer-poster img");
                  if (posterImg) coverUrl = absolutize(posterImg.getAttribute("src"));
                }
              }
              // 通用 fallback
              if (!coverUrl) {
                const metaSelectors = [
                  'meta[property="og:image"]',
                  'meta[property="og:image:url"]',
                  'meta[name="twitter:image"]',
                  'meta[name="twitter:image:src"]',
                ];
                for (const selector of metaSelectors) {
                  const value = document.querySelector(selector)?.getAttribute("content");
                  const url = absolutize(value);
                  if (url) { coverUrl = url; break; }
                }
              }
              if (!coverUrl) {
                const imageSelectors = [
                  'img[src*="tplv-dy"]',
                  'img[src*="douyinpic"]',
                  'img[src*="xhscdn"]',
                  'img[src*="sns-webpic"]',
                ];
                for (const selector of imageSelectors) {
                  const url = absolutize(document.querySelector(selector)?.getAttribute("src"));
                  if (url) { coverUrl = url; break; }
                }
              }
              return { title, coverUrl };
            },
          }).then(([result]) => {
            sendResponse({
              tabId: tab.id,
              url: tab.url ?? "",
              title: result?.result?.title || tab.title || "",
              coverUrl: result?.result?.coverUrl || "",
            });
          }).catch(() => {
            sendResponse({ tabId: tab.id, url: tab.url ?? "", title: tab.title ?? "", coverUrl: "" });
          });
        }).catch(() => {
          sendResponse({ tabId: null, url: "", title: "", coverUrl: "" });
        });
        return true;  // async
      }

      case "DOUYIN_AWEME_MAP_REPORT": {
        const added = addAwemeEntries(msg.entries || []);
        console.log(`[aweme-map] received ${msg.entries?.length || 0} entries, +${added} new, stats:`, getAwemeMapStats());
        if (added > 0) {
          chrome.runtime.sendMessage({
            type: "DOUYIN_AWEME_MAP_UPDATED",
            added,
            stats: getAwemeMapStats(),
          }).catch(() => {});
        }
        sendResponse({ ok: true, added });
        return false;
      }

      case "GET_AWEME_MAP_STATS": {
        sendResponse(getAwemeMapStats());
        return false;
      }

      default:
        return false;
    }
  });
}
