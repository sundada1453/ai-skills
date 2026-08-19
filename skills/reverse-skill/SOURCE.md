# reverse-skill 来源钉扎

本目录是 [zhaoxuya520/reverse-skill](https://github.com/zhaoxuya520/reverse-skill) 的完整快照，按本仓库约定 vendoring 到 `skills/reverse-skill/`。

| 项 | 值 |
|---|---|
| 上游 | https://github.com/zhaoxuya520/reverse-skill |
| 版本 | 1.0.1 |
| 提交 | 044224b00aeb0068ba56851d743a00165ebea2b7 |
| 上游日期 | 2026-08-19 |
| 同步日期 | 2026-08-20 |
| 许可证 | MIT（见本目录 `LICENSE`）；`CTF-Sandbox-Orchestrator/` 为 GPLv3 |

下次同步：

```bash
git clone --depth 1 https://github.com/zhaoxuya520/reverse-skill.git /tmp/reverse-skill
# 保留本仓库加的 SKILL.md / SOURCE.md
find skills/reverse-skill -mindepth 1 -maxdepth 1 \
  ! -name SKILL.md ! -name SOURCE.md -exec rm -rf {} +
tar -C /tmp/reverse-skill --exclude='.git' --exclude='.github' -cf - . \
  | tar -C skills/reverse-skill -xf -
# 然后更新本文件的提交 / 版本 / 日期
```

上游 Agent 入口仍是本目录内的 `README_AI.md`、`RULES.md` 和 `skills/SKILL.md`。本目录根上的 `SKILL.md` 只是为了让本仓库的技能索引能发现它。
