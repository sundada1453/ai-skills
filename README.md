# AI Skills 仓库

个人 AI Agent 技能（Skills）集合，兼容 Claude Code、Cursor、Codex、WorkBuddy、opencode 等任何遵循 SKILL.md 规范的编码智能体。每个 Skill 都是自包含目录，拷进 Agent 的技能目录即可使用。

当前收录：

| Skill | 说明 | 安装 |
|-------|------|------|
| [open-kimi-ppt](skills/open-kimi-ppt/) | 逆向 Kimi Slides 的非官方演示文稿 Skill，创建/编辑/复刻/读取并导出 PPT/PPTX；本版增强：支持读取/保存**服务器主机**目录 | 拷贝 `skills/open-kimi-ppt/` 到技能目录 |

---

# open-kimi-ppt（增强版）

逆向 Kimi Slides 实现的非官方演示文稿 Skill，让 AI Coding Agent 可以创建、编辑、复刻、读取并导出 PPT/PPTX。每次生成默认产出两份文件：可继续编辑的 PPTD 项目，以及带淡入淡出翻页切换的 PPTX。内置本地浏览器编辑器，可随时手动导出 PPTX。

> [!IMPORTANT]
> 本项目基于 MIT 开源项目 [binaryify/open-kimi-ppt-skill](https://github.com/binaryify/open-kimi-ppt-skill) 增强改造。原项目通过逆向分析 Kimi Slides Skill、PPTD 格式以及公开网页编辑器的前端行为与通信协议实现，并非 Kimi 或 Moonshot AI 的官方项目，也未获得其认可或支持。项目依赖的公开前端资源和兼容协议可能随 Kimi 更新而失效，仅供学习与研究使用。

## 本版相对原版的增强：主机目录桥

原版 `serve` 的「打开 PPTD 文件夹」只能使用浏览器 File System Access API 选择**用户自己电脑**上的目录。当编辑器部署在云服务器 / 远程主机上时，这个按钮无法触达服务器上的文件。

本版新增「**打开主机目录**」按钮：在编辑器顶栏点击后，弹出目录浏览器，可浏览并打开**运行服务的那台服务器**上的任意目录，找到 `.pptd` 直接加载；编辑后同样通过服务端接口保存回主机。本地文件夹按钮保留，两种模式互不干扰。

改动落在三处：

| 文件 | 改动 |
|------|------|
| `lib/editor-server.js` | 新增受限 `POST /ndfs/*` 接口：`list`（列目录）、`read`（读文本）、`read-image`（图片转 data URL）、`write`（保存文本） |
| `editor/index.html` | 顶栏新增「打开主机目录」按钮 + 目录浏览弹窗；离线拦截器对 `/ndfs/` 请求放行 |
| `editor/local-bridge.js` | 新增 host 模式：递归索引主机目录、走 `/ndfs` 读写，与本地模式无缝切换 |

## 安装

需要 Node.js 18 或更高版本（PPTX 导出 / `serve` 依赖），Python 3（导出脚本依赖）。

### 方式一：从本仓库拷贝

```bash
git clone https://github.com/sundada1453/ai-skills.git
cp -r ai-skills/skills/open-kimi-ppt ~/.agents/skills/
# 其他 Agent 目录：~/.codex/skills、~/.claude/skills、~/.cursor/skills、~/.workbuddy/skills 同理
```

### 方式二：直接使用当前已安装版本

当前 devbox 已安装到 `~/.agents/skills/open-kimi-ppt/`（含 patched WASM 与主机目录桥），其余 Agent 复用同一目录或按需复制。

### 更新

重新拉取仓库并覆盖拷贝即可。更新只替换 Skill 文件，不影响已生成的 PPTD / PPTX 项目。

## 使用

### 让 Agent 生成 PPT

安装完成后，直接向 Agent 描述需求即可。默认会同时生成完整的 PPTD 项目目录（可继续编辑）和对应的 PPTX 文件；只有明确要求只输出 PPTD 时才会跳过 PPTX 生成。

为了更稳定的出品，Prompt 里最好带上风格（如「深色产品发布风」），或附上参考 PPT 模板；只写主题、不给风格时效果更容易波动。

#### Prompt 示例

**示例：小米 SU7（约 8 页，素材取自官网，深色发布风）**

```text
使用 open-kimi-ppt 做一个介绍小米 SU7 的 PPT，素材从小米汽车官网找，约 8 页，深色产品发布风
```

本项目即用该流程产出过小米 SU7 宣传 PPT（`/workspace/xiaomi-su7-deck/`，8 页，覆盖外观、座舱、性能、续航、智能、安全）。

### 在线编辑与手动导出

建议直接让 AI 启动本地编辑器，例如说：

```text
帮我执行 node /workspace/skill/open-kimi-ppt/bin/open-kimi-ppt-skill.js serve
```

也可以自己在终端运行：

```bash
node skills/open-kimi-ppt/bin/open-kimi-ppt-skill.js serve
# 固定端口启动
node skills/open-kimi-ppt/bin/open-kimi-ppt-skill.js serve --port 55173
```

然后打开 <http://127.0.0.1:55173/>：

- **打开 PPTD 文件夹**：用浏览器 File System Access API 选择本地项目目录（`.pptd` + `pages/` + `media/`），Chromium 系浏览器可读写，其他浏览器回退只读上传；
- **打开主机目录**：本版增强，直接浏览服务器文件系统，输入绝对路径（如 `/workspace/xiaomi-su7-deck`）跳转，点 `.pptd` 加载，可编辑并保存回主机。

按 `Ctrl+C` 停止服务。

## 功能特性

- PPTD 生成：让 Agent 生成完整、可继续编辑的 PPTD 项目，支持从零创作、风格迁移、模板复用、图片/PDF 复刻。
- 元素动画：默认不加。提示词加上「要求带元素入场动画」即可，由 AI 按页编排合适的入场效果。
- PPTX 生成：默认同步生成 PPTX，写入淡入淡出翻页切换（与页内元素动画是两回事）；本地 WASM 导出全程离线。
- 视觉质检：多模态模型在导出 PPTX 前自动导出整份页面图片、拼接总览图逐项核查（变形、遮挡、出界、对比度、排版、文字溢出），问题页面修复后复检，直至全部通过。
- 在线编辑：通过浏览器查看和编辑本地 PPTD 项目，自动保存，可配置页面切换动画。
- 手动导出：在编辑器中随时手动导出 PPTX。
- 格式互转：将现有 PPTX 转换为 PPTD 后继续修改。
- 主机目录访问（本版增强）：在线编辑器可读取/保存运行服务的主机上的目录，适配云服务器 / 远程部署场景。
- 安全可控：本地编辑仅在用户明确授权的项目目录内读写文件。

## 为什么选 open-kimi-ppt

常见 PPT Skill 大致分三类：用代码库直接拼 OOXML / pptxgenjs、整页生成图片再塞进 PPTX、或输出网页 HTML 翻页。open-kimi-ppt 走的是 PPTD 中间层 + 真实可编辑 PPTX 这条路线，想让 Agent 好写、人好看、PowerPoint 能改。

| | open-kimi-ppt | 代码拼 PPTX（如 pptxgenjs） | 整页图片 PPT | 网页 HTML PPT |
| --- | --- | --- | --- | --- |
| 交付物 | PPTD 项目 + PPTX | 多为仅 PPTX | 多为仅 PPTX | 单文件 HTML |
| Agent 友好度 | YAML 逐页描述，结构清晰 | 坐标/API 细节多，易排版翻车 | 依赖出图模型与提示词 | HTML/CSS 模板约束强 |
| PowerPoint 可编辑 | 文本、形状、图片可继续改 | 可编辑，但难二次精修 | 整页位图，难改字 | 不是原生 PPTX |
| 视觉质量 | 真实版式 + 导出前多模态质检 | 依赖 Agent 手调布局 | 画面统一，偏海报感 | 动效强，适合演示分享 |
| 二次编辑 | 浏览器可视化编辑 + 自动保存 | 主要靠改代码重导出 | 基本需重新出图 | 改 HTML 源码 |
| 适用场景 | 要交可改的正式 PPTX，又要好看 | 结构化汇报、模板填充 | 视觉统一的海报风讲稿 | 浏览器内演讲 / 发布会 |

具体来说：

- PPTD 用 YAML 描述主题、布局与元素，比直接写 OOXML / pptxgenjs 更稳，也比整页渲一张图更方便局部修改。
- 默认同时交付两份文件：可继续迭代的 PPTD 项目，加上带淡入淡出翻页的 PPTX，不是只给半成品。
- 导出的 PPTX 里，文本框、形状仍可在 PowerPoint / WPS 中编辑，不像图片型 PPT 只能当海报。
- 浏览器里可以预览、微调、配置切换动画并再次导出，不用每次都让 Agent 重跑全流程。
- 导出前会做视觉质检：整页截图加总览图，检查遮挡、出界、对比度、溢出等问题，修完再出 PPTX。
- 不绑定官方模型，成本更低。可以在任意兼容 Agent 里使用 DeepSeek 等低成本模型；模型不支持多模态时，按 PPTD 规范生成也能做出像样的成品，有多模态时再做一遍视觉质检会更稳。

### 关于风格与主题

默认**不会**自动套用固定主题：未指定风格时由 Agent 按场景指南自行发挥。

> [!TIP]
> 建议在 Prompt 里写明 PPT 风格，或直接附上参考 PPT / PPTX 模板。有风格约束或模板参照时，效果会稳定不少；只给主题不给风格时，Agent 只能自行发挥，容易波动。

常见用法：

1. **在 Prompt 里描述风格**：例如「深色科技风」「杂志排版」「极简留白 + 大字报」；
2. **提供参考模板**：上传现有 PPT / PPTX / 截图，让 Agent 迁移配色、版式与风格。

## 什么是 PPTD

PPTD 是一种基于 YAML 的演示文稿 DSL，是 OOXML 之上的简化抽象层：保留主题、页面布局、元素位置等核心信息，去除了 Master 等复杂嵌套，每页自包含、所见即所得。完整的格式定义见 `reference/pptd.md`。

一个完整的 PPTD 项目目录结构如下：

```text
deck/
  deck.pptd     # 清单文件
  pages/        # 每页一个 .page 文件
  media/        # 本地媒体资源（如有）
  deck.pptx     # 默认同步生成的 PPTX 成品
```

## 工作原理与安全边界

- CLI 只在 `127.0.0.1` 启动静态文件服务，不会监听局域网地址。
- 浏览器只在用户主动授权后读取完整 PPTD 项目目录。
- 本地保存回调只允许修改 `.pptd` 和 `.page` 文件，并拒绝绝对路径与 `..` 路径越界。
- 默认编辑与 PPTX / 图片导出使用本地 neo-ppt 镜像 + patched WASM，**不依赖** `www.kimi.com`；远程图片、字体若被文稿引用仍可能从对应服务器加载。
- 视觉质检（`export_images.py`）与 `--browser` 路径驱动的是同一套本地编辑器（需本机 Chromium），不再访问公开 Kimi 站。
- 本项目不会提供或注入 Kimi 登录令牌，也不会访问用户的 Kimi 私有文稿。
- **主机目录接口（`/ndfs/*`，本版增强）**：仅监听本机，白名单约束写入——`read` 限文本扩展名（`.pptd/.page/.yaml/.yml/.json/.md/.txt/.csv/.jsonl`，≤2MB），`read-image` 限图片扩展名（png/jpg/jpeg/gif/webp/svg，≤20MB），`write` 仅允许 `.pptd/.page`。接口无认证，仅应在可信网络 / 本机使用。

## 本地开发

```bash
cd skills/open-kimi-ppt
npm install --global .
npm test
```

## 新增 Skill 约定

本仓库用于长期积累个人 Skill，新增时遵循：

1. 每个 Skill 一个自包含目录，放在 `skills/<skill-name>/`；
2. 目录内必须有 `SKILL.md`，含 `name` 与 `description` frontmatter；
3. 更新上方索引表格与 README 对应章节；
4. 建议在 Skill 目录内自带 `README.md` 说明部署、依赖与改动点。

## 声明

Kimi、Kimi Slides 及相关商标归其权利人所有。本仓库内 Skill 保留其上游项目许可证（MIT），修改与再分发请保留原 LICENSE 声明。
