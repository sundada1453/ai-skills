# AI Skills 仓库

个人 AI Agent 技能（Skills）集合，兼容 Claude Code、Cursor、Codex、WorkBuddy、opencode 等任何遵循 SKILL.md 规范的编码智能体。每个 Skill 都是自包含目录，拷进 Agent 的技能目录即可使用。

## 目录结构

```text
ai-skills/
├── README.md                  # 本索引
└── skills/
    └── open-kimi-ppt/         # 第一个 skill：open-kimi-ppt 增强版（详见其目录内 README）
```

## Skills 索引

| Skill | 说明 | 详细文档 |
|-------|------|----------|
| [open-kimi-ppt](skills/open-kimi-ppt/) | 逆向 Kimi Slides 的非官方演示文稿 Skill，创建/编辑/复刻/读取并导出 PPT/PPTX；本版增强：支持读取/保存**服务器主机**目录 | [skills/open-kimi-ppt/README.md](skills/open-kimi-ppt/README.md) |

## 安装方法

每个 Skill 是自包含目录，拷贝到你的 Agent 技能目录即可：

```bash
# Claude Code / Cursor / Codex / WorkBuddy / opencode 通用（示例 ~/.agents/skills）
cp -r skills/<skill-name> ~/.agents/skills/
```

open-kimi-ppt 的完整安装、使用、Prompt 示例与安全说明见 [skills/open-kimi-ppt/README.md](skills/open-kimi-ppt/README.md)。

## 新增 Skill 约定

1. 每个 Skill 一个自包含目录，放在 `skills/<skill-name>/`；
2. 目录内必须有 `SKILL.md`，含 `name` 与 `description` frontmatter；
3. 详细说明写在 Skill 目录内的 `README.md`，本文件只更新索引表；
4. 保留各 Skill 上游项目许可证（见目录内 LICENSE / README 声明）。

## 授权

- 各 Skill 保留其上游项目许可证（如 open-kimi-ppt 为 MIT，见其目录内 README 授权节）
- 本仓库结构、索引与增量修改按需选用开源许可
