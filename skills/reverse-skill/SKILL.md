---
name: reverse-skill
description: 逆向 / 授权渗透 / 安全研究技能路由包。APK、二进制、前端 JS、CTF、固件、恶意软件、API、供应链、LLM 安全等任务先走此入口，由 41 条规则路由到对应子 skill。仅用于你拥有或已获书面授权的系统。
---

# reverse-skill

Vendored snapshot of [zhaoxuya520/reverse-skill](https://github.com/zhaoxuya520/reverse-skill) **v1.0.1** (`044224b`). 钉扎信息见 [SOURCE.md](SOURCE.md)。

**仅用于合法安全研究、教学、CTF，以及你拥有或已获明确书面授权的系统。未授权扫描 / 利用一律禁止。**

## CRITICAL：读完立刻执行

不要只回复“已读”。按顺序：

1. 读 [README_AI.md](README_AI.md) 和 [RULES.md](RULES.md)（授权门，`auth` 未 granted 禁止对目标 ACT）。
2. 打开真正的路由入口：[skills/SKILL.md](skills/SKILL.md)。
3. 跑平台原生 router：
   - Linux/macOS：`bash skills/scripts/master-route.sh`
   - Windows：`powershell -File skills/scripts/master-route.ps1`
4. `case-init` 落地 `work/<case>/scope.md`；本地离线样本用 `offline-sample` preset。
5. 打开 PRIMARY 子 skill 的 `SKILL.md` 执行 ACTION REQUIRED。
6. 工具路径只认 [skills/tool-index.md](skills/tool-index.md)；缺工具走平台 bootstrap。

相对路径一律相对**本目录**（`skills/reverse-skill/`），不是仓库根。

## 这个包里有什么

41 条路由规则（R0–R40）+ 42 个场景模块，包括：

| 方向 | 入口 |
|------|------|
| APK / Android | `skills/apk-reverse/` |
| iOS / 移动 | `skills/mobile-reverse/` |
| 二进制 (exe/dll/so/elf) | `skills/ida-reverse/` / `skills/ghidra-reverse/` / `skills/radare2/` |
| 前端 JS / 签名 | `skills/js-reverse/` |
| .NET | `skills/dotnet-reverse/` |
| 恶意软件 | `skills/malware-analysis/` |
| 授权渗透 | `skills/pentest-tools/` / `skills/attack-chain/` |
| CTF | `CTF-Sandbox-Orchestrator/` |
| 固件 / IoT | `skills/firmware-pentest/` |
| Pwn | `skills/pwn-chain/` |
| API / 供应链 / LLM | `skills/api-security/` / `skills/supply-chain-security/` / `skills/llm-security/` |

完整矩阵：[skills/routing.md](skills/routing.md) · 快梯：[skills/MASTER-ROUTING.md](skills/MASTER-ROUTING.md)

## 安装

```bash
cp -r skills/reverse-skill ~/.agents/skills/
```

然后按平台刷新工具索引：

| 平台 | 命令 |
|------|------|
| Linux / macOS | `bash skills/scripts/refresh-tool-index.sh` |
| Windows | `powershell -File skills/scripts/refresh-tool-index.ps1` |
| Kali | `bash kali/scripts/refresh-tool-index.sh` |
