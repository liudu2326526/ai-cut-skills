// 给抖音/快手等 CDN 的下载请求注入 Referer。
// chrome.downloads.download 调用 CDN URL 时不会带 Referer，CDN 会拒绝返回 HTML 错误页。
// 用 declarativeNetRequest 动态规则在网络层补上 Referer。

const RULES = [
  {
    id: 1001,
    priority: 1,
    action: {
      type: "modifyHeaders",
      requestHeaders: [
        { header: "Referer", operation: "set", value: "https://www.douyin.com/" },
      ],
    },
    condition: {
      requestDomains: [
        "douyinvod.com",
        "douyincdn.com",
        "bytefcdnrd.com",
        "zjcdn.com",
        "amemv.com",
        "feishucdn.com",
      ],
    },
  },
  {
    id: 1002,
    priority: 1,
    action: {
      type: "modifyHeaders",
      requestHeaders: [
        { header: "Referer", operation: "set", value: "https://www.kuaishou.com/" },
      ],
    },
    condition: {
      requestDomains: ["yximgs.com", "kuaishouzt.com"],
    },
  },
];

export async function initRefererInjector() {
  try {
    const existing = await chrome.declarativeNetRequest.getDynamicRules();
    const existingIds = existing.map((r) => r.id);
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: existingIds,
      addRules: RULES,
    });
    const installed = await chrome.declarativeNetRequest.getDynamicRules();
    console.log("[referer-injector] installed:", installed.length, "rules");
    for (const rule of installed) {
      console.log("[referer-injector]   rule", rule.id, "domains:", rule.condition?.requestDomains);
    }
  } catch (err) {
    console.error("[referer-injector] FAILED to install rules:", err);
  }
}
