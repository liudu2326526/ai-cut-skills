# AI 审查建议与人工合并

本仓库不再使用 AI 自动合并。此文档保留原路径，避免旧链接失效。

## 工作流程

1. `PR Checks` 在 PR 代码上执行测试、语法检查和增量安全扫描，只有只读权限，外部 Fork 无法读取 Secret。
2. `AI Review Suggestions` 在 `PR Checks` 成功后，通过 `workflow_run` 从 `main` 加载可信审查脚本；不检出、不执行 PR 代码。它核对当前 PR head SHA、来源仓库/分支、可信账号、CI 作业和 diff，再调用 AI。
3. AI 在 PR 评论中给出摘要、P0–P3 修改建议和审查限制，注明被审查的完整 head SHA。所有严重级别均为建议，不构成批准或驳回，不设置 `ai-review/gate` 状态，也不调用任何合并接口。
4. 维护者结合建议与必需 CI 检查，最终手动合并。

新建议会更新原有机器人审查评论，替换旧的 PASS/BLOCK 展示。发布前再次核对 head SHA；PR 已关闭或出现新提交时，丢弃过期结果，不覆盖新提交的评论。

缺少配置、API 超时、输出无效、来源未验证、凭据文件、二进制/截断 diff、超出输入限制等情况，只表示 AI 审查未完成；能定位当前 PR 时会评论说明。工作流可因这些运行错误显示失败，但它不是必需检查，**不阻止人工合并**，也不能被当作审查通过。API 调用前失败且无法定位 PR 的错误仅记录在 Actions 日志中。

## 仓库配置

Actions Secret：

- `AI_REVIEW_API_KEY`：AI 服务密钥，仅存入 GitHub Actions Secret。

Actions Variables：

- `AI_REVIEW_BASE_URL`：OpenAI Responses API 兼容地址，必须使用 HTTPS。
- `AI_REVIEW_MODEL`：审查模型 ID，当前使用 `gpt-5.6-sol`。
- `AI_REVIEW_TIMEOUT_SECONDS`：单次 AI 审查读取超时，默认 `300` 秒，允许 `30`–`900` 秒。
- `AI_REVIEW_TRUSTED_ACTORS`：允许自动调用 AI 的 GitHub 登录名，逗号分隔；作者和 head 仓库所有者都必须命中。这是凭据使用和调用成本的边界，不是合并许可。

主分支仍要求 PR、分支为最新、禁止强推、禁止删除、禁止管理员绕过。只把以下状态设置为必需检查：

- `test`
- `lint`
- `security-scan`

**不要**把 `ai-review/gate` 或 `review-suggestions` 设置为必需检查。仓库 `Allow auto-merge` 必须关闭，现有 PR 的自动合并请求也必须取消。AI 工作流仅有 `actions: read`、`contents: read`、`pull-requests: read` 和 `issues: write` 权限；评论是唯一写入用途，没有提交代码、发布状态、批准/驳回 PR 或合并权限。

## 审查边界

工作流、脚本等自动化基础设施也可以作为文本接收建议，但不会执行 PR 中的内容。仍拒绝把疑似凭据文件（如 `.env*`、私钥）、无法完整读取的 diff 或非普通文件发送到 AI；单次上限为 80 个文件、5,000 行变动、160,000 字符 patch，最终请求内容也受 160,000 字符限制。草稿 PR 和未通过 `PR Checks` 的变更不自动调用 AI。

## 从自动合并模式迁移

1. 暂停旧的 `AI Review And Merge` 工作流，取消未完成的旧运行与所有 PR 自动合并请求，关闭仓库 `Allow auto-merge`。
2. 从分支保护中移除 `ai-review/gate`，保留三个必需 CI 检查和其他保护设置。
3. 设置 `AI_REVIEW_TRUSTED_ACTORS`，沿用已有服务密钥、接口、模型与超时配置。
4. **由维护者手动合并**建议模式配置 PR。此 PR 删除旧工作流，新增 `ai-review-suggestions.yml`，避免继承旧工作流的暂停状态。
5. 新工作流进入 `main` 后，后续 `PR Checks` 成功的 PR 会收到建议。需要为已有 PR 重新审查时，重跑该 PR 当前 head 的 `PR Checks`；过期运行不会用于审查新 head。

配置 PR 合并前，旧 AI 工作流保持暂停，不会产生新的建议或执行合并；人工合并与必需 CI 不受影响。旧的失败状态仍可能保留在提交历史中，但已不再是合并门禁。
