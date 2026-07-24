const TAG = "[douyin-bridge]";
console.log(TAG, "installed on", location.href);

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.origin !== location.origin) return;
  if (!event.data?.__aivideo_douyin_aweme_map_report__) return;

  const entries = event.data.entries;
  if (!Array.isArray(entries) || entries.length === 0) return;

  console.log(TAG, `forwarding ${entries.length} entries to background`);
  chrome.runtime.sendMessage({
    type: "DOUYIN_AWEME_MAP_REPORT",
    entries,
  }).catch((err) => console.warn(TAG, "sendMessage failed", err));
});
