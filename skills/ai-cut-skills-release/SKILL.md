---
name: ai-cut-skills-release
description: "提交 AI Cut Skills 仓库改动并创建或更新 GitHub PR；适用于按组别和日期建分支、执行 Skill 校验、提交变更和推送 PR。"
---

# AI Cut Skills Release

这个 Skill 只处理当前 `ai-cut-skills` 仓库的提交和 GitHub PR 创建。默认执行只读预检；只有用户明确要求提交时才使用 `--execute`。

## 工作流

1. 明确目标 Skill、组别、变更类型和摘要。
2. 从 `upstream/main` 获取最新基线，创建 `<组别>/<类型>-<作用域>-<YYYYMMDD>` 分支。
3. 只带入目标 Skill 及显式指定的附加文件，不把其他工作区改动混入提交。
4. 执行 Skill 结构校验、仓库清单校验、语法检查和现有测试。
5. 生成规范 commit，推送到 `origin`，创建或更新对应 GitHub PR。
6. 重复执行同一组别/作用域/日期时，只允许在检测到当前账户、当前 base 分支下的打开 PR 后安全更新远端分支；陌生的同名远端分支会直接停止。

## 认证

使用本机现有的 GitHub CLI 登录态或 Git Credential Manager/SSH Agent。通过 `--github-account` 可以校验登录账户；不要把 GitHub 密码、Token 或私钥写入参数、配置、任务文件、日志或 PR 内容。

## 命令

预检（不创建分支、不提交、不推送）：

```powershell
python skills/ai-cut-skills-release/scripts/submit_pr.py `
  --skill aivideoeditor-usergrowth-automation `
  --group 014-code `
  --change-type fix `
  --summary "restore ARLP platform multi-select" `
  --github-account 014-code
```

执行提交并创建 PR：

```powershell
python skills/ai-cut-skills-release/scripts/submit_pr.py `
  --skill aivideoeditor-usergrowth-automation `
  --group 014-code `
  --change-type fix `
  --summary "restore ARLP platform multi-select" `
  --github-account 014-code `
  --execute
```

多个 Skill 或测试文件需要显式重复 `--skill` / `--include`。没有目标变更、校验失败、GitHub 账户不匹配、远端同名分支没有可复用的打开 PR，或 PR 已产生不可安全判断的冲突时停止并报告，不覆盖现有工作。

执行模式保持可审计：默认只读预检；`--execute` 才创建临时 worktree、提交和推送。已有受管 PR 的分支更新使用 `git push --force-with-lease`，不会无条件强制覆盖远端分支。这个 Skill 只创建或更新 PR，不自动审批或合并。

详细的分支、提交范围和 PR 规则见 [references/release-policy.md](references/release-policy.md)。
