# open-kimi-ppt · 增强版（Host-FS Bridge）

基于 MIT 协议开源项目 [binaryify/open-kimi-ppt-skill](https://github.com/binaryify/open-kimi-ppt-skill) 的本地增强版。

## 核心改动：支持读取/保存服务器（主机）上的目录

原版 `serve` 的「打开 PPTD 文件夹」仅能用浏览器 File System Access API 选择**用户自己电脑**上的目录。
本版新增「打开主机目录」按钮，可浏览并打开**运行服务的那台服务器**上的目录——适合部署在云服务器/远程环境中的场景。

### 改动清单

| 文件 | 改动 |
|------|------|
| `lib/editor-server.js` | 新增受限 `POST /ndfs/*` 接口：`list`（列目录）、`read`（读文本，白名单扩展名 ≤2MB）、`read-image`（图片转 data URL ≤20MB）、`write`（仅 `.pptd`/`.page`） |
| `editor/index.html` | 顶栏新增「打开主机目录」按钮 + 目录浏览弹窗；离线拦截器对 `/ndfs/` 请求放行（修复 `/list$` 正则误拦截） |
| `editor/local-bridge.js` | 新增 host 模式：递归索引主机目录、走 `/ndfs` 读取文本/图片、保存回主机，与本地模式无缝切换 |
| `editor/local-shell.css` | 弹窗与列表样式 |

### /ndfs 安全限制

- `read`：仅白名单扩展名（`.pptd/.page/.yaml/.yml/.json/.md/.txt/.csv/.jsonl`），≤2MB
- `read-image`：仅 `.png/.jpg/.jpeg/.gif/.webp/.svg`，≤20MB
- `write`：仅 `.pptd`/`.page`，自动建目录
- 无认证——仅在可信网络内使用

## 部署

```bash
# 启动编辑器（固定端口 55173）
node /workspace/skill/open-kimi-ppt/bin/open-kimi-ppt-skill.js serve --port 55173
# 或
/workspace/skill/open-kimi-ppt/bin/open-kimi-ppt-skill.js serve

# 导出 PPTX（本地 WASM，离线）
python3 scripts/export_pptx.py /abs/path/deck.pptd --output /abs/path/deck.pptx

# 图片 QA（需 Chromium，可选）
python3 scripts/export_images.py /abs/path/deck.pptd --output /abs/path/.qa-images
```

## 开机自启（本环境已配置）

- SysV init 脚本：`/etc/init.d/neodeck`（`start|stop|restart|status`），已注册 `update-rc.d`
- 备用钩子：`/etc/rc.local`

> 注意：本 devbox 的 PID 1 为定制 `firecracker-init`，若其不执行 rc 流程，重启后需手动
> `/etc/init.d/neodeck start` 或 `node bin/open-kimi-ppt-skill.js serve` 拉起服务。

## 授权

- 原始代码 © binaryify，MIT License
- 本增强基于原项目，保留原 LICENSE 声明
- 发布到自己的 GitHub 仓库时，请保留 MIT 许可并注明修改自原项目
