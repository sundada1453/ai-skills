# AI Skills 仓库

个人 AI Agent 技能（Skills）集合，供 Claude Code / Cursor / Codex / opencode 等编码智能体复用。

## 目录结构

```
ai-skills/
├── README.md
└── skills/
    └── open-kimi-ppt/      # 第一个 skill：open-kimi-ppt 增强版
```

## Skills 索引

| Skill | 说明 | 安装 |
|-------|------|------|
| [open-kimi-ppt](skills/open-kimi-ppt/) | PPTD 演示文稿创建/编辑/导出（Kimi PPT 本地镜像），增强版支持读取/保存**服务器主机**目录 | 复制 `skills/open-kimi-ppt/` 到 `~/.agents/skills/`（或对应 agent 的 skills 目录） |

## 安装方法

每个 skill 是自包含目录，拷贝到你的 agent 技能目录即可：

```bash
# Claude Code / Cursor / Codex / opencode 通用（示例 ~/.agents/skills）
cp -r skills/<skill-name> ~/.agents/skills/
```

## 新增 Skill 约定

1. 每个 skill 一个目录，自包含（含 `SKILL.md`、脚本、资源）
2. 目录内必须有 `SKILL.md`，含 `name` 与 `description` frontmatter
3. 在下方索引表格补充一行
4. 建议在 skill 目录内自带 `README.md` 说明部署与依赖

## 授权

- 各 skill 保留其上游项目许可证（见各目录内 LICENSE 或 README 声明）
- 本仓库结构、索引与增量修改按需选用开源许可
