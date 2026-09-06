# vendored skill · neat-freak

| | |
|---|---|
| 原名 | neat-freak（洁癖） |
| 上游 | https://github.com/lsa03/neat-freak-person |
| License | MIT（`LICENSE-upstream.md`）|
| 引入 commit | `089372f9` （2026-06-21）|
| 引入日期 | 2026-09-06 |
| 安装位置 | **`.agents/skills/neat-freak/`**（Agent Skills 开放标准，agentskills.io）|

## 本工作目录的安装状态

**2026-09-06 核对：只存在 `.agents/skills/neat-freak/` 这一份；没有 `.claude/skills/`，也没有符号链接。**
具备文件读取权限的 agent 可直接读取 `SKILL.md` 及其引用文件执行流程；各客户端是否自动发现，取决于其版本与配置，不能据此声称全部兼容性测试已通过。

上游 `SKILL.md`、`references/` 与许可证保持原样；**本文件是项目自己的溯源 / 安装说明，可随实际目录状态更新**。
上游参考文档中的跨平台目录和初始化示例不是本项目的现状；项目约束以根目录 `AGENTS.md` 为准。

**以下升级 / 安装命令为可选维护操作，Bash 环境、从项目根目录执行；本次审计未执行。**
升级方式（会覆盖本地副本）：

```bash
git clone --depth 1 https://github.com/lsa03/neat-freak-person.git /tmp/nf \
  && rm -rf .agents/skills/neat-freak/SKILL.md .agents/skills/neat-freak/references \
  && cp -r /tmp/nf/skill/SKILL.md /tmp/nf/skill/references .agents/skills/neat-freak/ \
  && cp /tmp/nf/LICENSE .agents/skills/neat-freak/LICENSE-upstream.md \
  && rm -rf /tmp/nf
```

装到用户级（所有项目可用）时复制这一份，**不要在本仓库维护第二份副本**：

```bash
mkdir -p ~/.agents/skills && cp -r .agents/skills/neat-freak ~/.agents/skills/   # Codex / Cursor / Copilot / OpenCode
mkdir -p ~/.claude/skills && cp -r .agents/skills/neat-freak ~/.claude/skills/   # Claude Code
```

> **Windows 用户**：当前目录没有需要修复的符号链接。若客户端不能自动发现，可显式让 agent 读取这份 skill；需要客户端专用安装时，按该客户端文档另行配置，不虚构已安装状态。
