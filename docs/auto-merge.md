# 安全自动审查与合并

本仓库使用两段式 GitHub Actions 流程：

1. `PR Checks` 在 PR 代码上执行测试、语法检查和增量安全扫描。该流程只有只读权限，外部 Fork 无法读取 Secret。
2. `AI Review And Merge` 通过 `workflow_run` 从 `main` 加载可信门禁代码，不检出或执行 PR 代码。它重新读取 GitHub 当前状态、校验 PR head SHA、可信账号、文件范围、CI 作业和 diff，再调用 AI 审查。

只有确定性门禁和 AI 审查都通过，流程才会为同一个 head SHA 开启 squash auto-merge，并发布 `ai-review/gate` 状态。任何缺少密钥、API 错误、SHA 变化、二进制/截断 diff、冲突、非可信作者或敏感路径修改都会失败关闭。

## 仓库配置

Actions Secret：

- `AI_REVIEW_API_KEY`：AI 服务密钥。

Actions Variables：

- `AI_REVIEW_BASE_URL`：OpenAI Responses API 兼容地址，必须使用 HTTPS。
- `AI_REVIEW_MODEL`：审查模型 ID。
- `AI_REVIEW_TIMEOUT_SECONDS`：单次 AI 审查读取超时，默认 `300` 秒，允许 `30`–`900` 秒。
- `AUTO_MERGE_TRUSTED_ACTORS`：允许自动合并的 GitHub 登录名，逗号分隔；作者和 head 仓库所有者都必须命中。

主分支必须要求 PR，并把下列状态设置为 required checks：

- `test`
- `lint`
- `security-scan`
- `ai-review/gate`

同时要求分支为最新、禁止强推、禁止删除、禁止管理员绕过。只有 `README.md`、`LICENSE`、`skill-catalog.yaml`、`skills/**` 和 `tests/**` 进入自动合并候选；Workflow、门禁脚本、CI 依赖、凭据文件和二进制/截断 diff 必须人工审查。

## 修改门禁自身

`.github/**`、`scripts/**`、`requirements-ci.txt` 等自动化基础设施不会被自动门禁放行。修改这些文件时，使用人工审查的 PR；合并后再用一个普通 Skill PR 验证端到端流程。
