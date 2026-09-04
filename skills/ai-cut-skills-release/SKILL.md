---
name: ai-cut-skills-release
description: "提交 AI Cut Skills 仓库改动并创建或更新 GitHub PR；适用于按组别和日期建分支、执行 Skill 校验、提交变更和推送 PR。"
---

# AI Cut Skills Release

这个 Skill 只处理当前 `ai-cut-skills` 仓库的提交和 GitHub PR 创建。默认执行只读预检；只有用户明确要求提交时才使用 `--execute`。

## 工作流

1. 明确目标 Skill、组别、变更类型和摘要。
2. 从 `upstream/main` 获取最新基线，创建 `<组别>/<类型>-<作用域>-<YYYYMMDD>` 分支。
3. 执行模式默认检查当前 GitHub 账户是否已有目标仓库的 fork；没有时自动创建，并等待 fork 可用。
4. 只带入目标 Skill 及显式指定的附加文件，不把其他工作区改动混入提交；符号链接路径会被拒绝，避免把仓库外文件复制进提交。
5. 执行 Skill 结构校验、语法检查和 Git 差异检查；仓库清单与测试由 GitHub PR Checks 在其受控工作流中执行，发布脚本本地不运行仓库脚本和测试。计划模式同样只执行静态/可信校验，也不刷新远端引用。
6. 生成规范 commit，推送到当前账户 fork，创建或更新对应 GitHub PR。
7. 重复执行同一组别/作用域/日期时，只允许在检测到当前账户、当前 base 分支下的打开 PR 后安全更新远端分支；PR 创建 API 返回不确定时保留带有受管提交标记的远端分支，后续可安全重试，陌生的同名远端分支会直接停止。

## 认证

使用本机现有的 GitHub CLI 登录态或 Git Credential Manager/SSH Agent。通过 `--github-account` 可以校验登录账户；不要把 GitHub 密码、Token 或私钥写入参数、配置、任务文件、日志或 PR 内容。
自动 fork 通过 GitHub CLI 完成，仍然只使用登录态，不接受或保存密码。已有的 `origin`（或 `--push-remote` 指定远端）如果缺失会添加为当前账户 fork；如果已指向其他仓库则停止，不自动改写。

## 命令

预检（不创建分支、不提交、不推送；不会运行仓库脚本或测试）：

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

多个 Skill 或测试文件需要显式重复 `--skill` / `--include`。发布目标固定为规范仓库 `liudu2326526/ai-cut-skills`；`--target-repository` 只能显式指定该仓库，不能通过自定义 remote 或参数改向其他仓库。没有目标变更、校验失败、GitHub 账户不匹配、远端同名分支没有可复用的打开 PR，或 PR 已产生不可安全判断的冲突时停止并报告，不覆盖现有工作。

如需跳过 GitHub fork 的创建和 parent 校验，可显式增加 `--no-auto-fork`。该选项仍会严格校验推送远端的 fetch URL 和所有有效 push URL 必须指向当前账户 fork，不会放宽提交范围、分支和 PR 安全校验。

执行模式保持可审计：默认只读预检；`--execute` 先在临时 worktree 中完成变更范围、Skill 校验和静态检查，仓库脚本和测试由 GitHub PR Checks 执行；全部通过后才创建/确认 fork、修改 push remote、提交和推送。commit/push 使用临时空 hooks 目录，不执行仓库自带 hooks。摘要会经过单行和凭据模式校验，疑似包含密钥时拒绝写入 commit 或 PR。空变更或校验失败不会产生 GitHub 或本地 remote 配置副作用。已有受管 PR 的更新以远端 PR 分支作为 worktree 基线，只应用当前工作区差异；本地若有远端之后的新提交则仅应用这些增量，分支分叉时停止。更新使用 `git push --force-with-lease`，提交后会再次核验实际 commit 的变更范围；与最新基线无法安全合并时停止。这个 Skill 只创建或更新 PR，不自动审批或合并。

详细的分支、提交范围和 PR 规则见 [references/release-policy.md](references/release-policy.md)。
