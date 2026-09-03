# Release Policy

## 分支

分支名由命令参数生成：

```text
<group>/<change-type>-<scope>-<YYYYMMDD>
```

`group` 必须是安全的 Git 分支前缀，例如 `014-code`；`scope` 默认由目标 Skill 名称组成，也可以用 `--scope` 覆盖。日期默认使用本地当天日期，测试或补交历史改动时可以用 `--date YYYYMMDD` 指定。

## 变更范围

目标 Skill 通过重复的 `--skill` 指定，额外测试或清单文件必须通过 `--include` 明确指定。脚本会从最新基线重建临时 worktree，再把这些路径的已提交、已暂存和未暂存差异应用到新分支，避免把当前工作区的其他改动带入 PR。

运行时缓存、编译产物和其他未列入允许范围的文件不会被提交。

## 校验

提交前依次执行：

- `quick_validate.py` 校验每个目标 Skill 的 frontmatter、目录和占位内容；
- `scripts/sync_skills.py --check` 校验仓库 catalog；
- Python 文件语法检查；
- `git diff --check`；
- 仓库 `tests/` 下的 unittest（可用 `--skip-tests` 明确跳过）。

任何失败都会阻止 commit 和 push。校验结果会写入 PR 描述，不写入凭据。

## GitHub PR

仓库当前以 `upstream` 作为 PR 基线，以 `origin` 作为推送远端。脚本从 upstream remote 解析目标仓库，使用 GitHub CLI 当前登录账户作为 head owner；`--github-account` 仅用于账户一致性校验。

同一 head 分支已有打开的 PR 时更新标题和正文，不重复创建。执行前会先检查远端是否已有同名分支；临时 worktree 结束后会清理脚本创建的本地分支引用：

- 没有远端分支：使用普通 `git push`；
- 有远端分支且存在当前账户指向目标 base 的打开 PR：只用 `--force-with-lease=<expected-sha>` 更新；
- 有远端分支但没有可复用的打开 PR：停止，避免覆盖未知改动。

PR 创建和更新都要求 GitHub CLI 已登录并具备目标仓库权限。PR 的 head owner、head branch 和 base branch 必须与本次执行一致。

合并不属于本 Skill 的自动动作；提交 Skill 只负责生成可审查的 PR。
