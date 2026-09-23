# 小波标书助手V9.0 便携技能包

本仓库为「小波标书助手V9.0」智能体技能的便携发行包，专为上传至 GitHub 分发及跨环境导入智能体工作流设计。

- **技能名称**：小波标书助手V9.0 (`bobobiaoshu-skill`)
- **原技能路径**：`/home/box/agent-data/workflows/bobobiaoshu-skill/`
- **版本**：`V9.0.0`
- **适用场景**：技术标编写、交通工程（高速/航道）投标、信息化项目投标、安全规划方案投标等
- **触发词**：写标书、投标、技术标、招标文件、投标文件、技术方案、终稿

---

## 1. 技能定位与核心功能

「小波标书助手V9.0」是一套完整的投标文件技术标自动生成工具链。其核心理念是**以招标文件为基准、以评分标准为导向、以专业模板为载体、以去 AI 痕迹为保障**，全自动化辅助编写高质量、符合专家评审习惯的技术标方案。

### 核心能力特性
1. **三级解析招标文件**：
   - 第一级：本地解析（基于 `python-docx`、`pdfplumber`、`openpyxl`，快速稳定）；
   - 第二级：MarkItDown 解析（复杂格式降级支持）；
   - 第三级：星辰 OCR（扫描件 PDF 及图片解析）。
2. **招标文件深度分析**：
   - 生成涵盖项目信息、时间节点、采购需求、评分标准、商务条款、投标重点、技术难点、风险提示、特别条款、竞争态势的 10 节深度分析报告。
3. **评分点自动映射与覆盖闭环**：
   - 自动提取评分指标，智能匹配到对应章节并计算字数分配，确保“每分必应、无一遗漏”。
4. **【★必做】必含标题检测**：
   - 针对招标文件中“包括但不限于”、“至少包含”等强制性条款进行规则抽取，强制映射为 H2 标题并做覆盖率审计。
5. **Token / 耗时预估**：
   - 在生成大纲阶段即预测总体输入/输出 Token 量与编写时间，支持常规文本模式与图表/表格丰富模式（Token +15%）。
6. **基于模板的 Word 格式渲染**：
   - 读取用户提供的 Word 模板排版格式，自动注入标题编号（numPr），实现样式完全贴合。
7. **去 AI 痕迹与质量双轨检测**：
   - 内置红旗词词典与人类化中文改写策略（上下文感知替换），杜绝“综上所述”、“显而易见”等典型 AI 语病；
   - 提供内容相关性、一致性、字数达标率及历史项目词汇残留排查。

---

## 2. 目录结构

```
bobobiaoshu-skill/
├── README.md                  # 本说明文档（便携包说明、环境依赖、快速上手）
├── SKILL.md                   # 技能核心提示词与执行规范流程（全流程标准）
├── _skillhub_meta.json        # SkillHub 技能包元数据
├── biaoshu_workflow.drawio    # 标书生成完整工作流架构图（Draw.io 格式）
├── references/                # 写作规范与去 AI 痕迹理论参考
│   ├── de-ai-rules.md         # 去 AI 痕迹速查规则与红旗词词典
│   └── humanizer-zh.md        # 中文自然语言写作与人类化指南
└── scripts/                   # 核心 Python 脚本与辅助工具集
    ├── bid_analysis.py            # 招标文件深度分析（10节报告）
    ├── check_chapter_words.py     # 章节字数达标检查
    ├── config_manager.py          # 首次运行配置与记忆库初始化
    ├── consistency_check.py       # 标书正文前后一致性检查
    ├── convert_to_word.py         # Markdown 转专业 Word 文档（支持模板与编号注入）
    ├── doc_quality_check.py       # 文档综合质量全面审查
    ├── estimate_tokens.py         # Token 消耗量与编写耗时预测
    ├── eval_mapping.py            # 评分标准智能映射与覆盖表生成
    ├── eval_required_headings.py  # 必含/强制标题抽取与覆盖检查
    ├── macos_compat.py            # macOS 平台跨平台兼容适配（字体/路径）
    ├── macos_setup.sh             # macOS 快速环境配置脚本
    ├── merge_chapters.py          # 多章节 Markdown 汇总合并
    ├── parse_bid_files.py         # 招标文件三级自适应解析器
    ├── relevance_check.py         # 内容与招标文件相关性及污染检测
    ├── snippet_adapt.py           # 历史片段适配与原项目残留排查
    ├── snippet_manager.py         # 优秀方案片段库检索与入库管理
    └── template_extractor.py      # Word 模板排版样式与元数据提取
```

---

## 3. 环境要求与依赖安装

本技能基于 Python 3.8+ 开发（推荐 Python 3.10 / 3.11 / 3.12）。

### 3.1 核心依赖（必须）

```bash
pip install python-docx pdfplumber openpyxl PyPDF2
```

依赖说明：
- `python-docx`：Word 模板解析、样式提取、技术标正文生成与标题编号注入；
- `pdfplumber`：高精度解析 PDF 招标文件（提取表格与正文结构）；
- `openpyxl`：解析 Excel 格式的招标文件工程量清单或评分表；
- `PyPDF2`：PDF 元数据读取与常规流解析。

### 3.2 进阶/可选依赖

```bash
# 二级文档解析扩展（可选）
pip install "markitdown[all]"
```

### 3.3 macOS 用户一键配置

针对 macOS 开发者，技能自带一键配置脚本与字体映射兼容层：

```bash
bash scripts/macos_setup.sh
```

---

## 4. 标准执行流程（18 步）

```
⓪ 首次配置：config_manager.py check（首次配置引导或自动加载配置）
① 接收输入：招标文件 + 用户提供的 Word 模板
② 交互确认：询问目标页数、是否插入正文图表/表格
③ 三级解析：parse_bid_files.py 提取文字与表格结构
④ 深度分析：bid_analysis.py 生成 10 节招标文件分析报告
⑤ 评分映射：eval_mapping.py 建立评分项与章节对应矩阵及字数规划
⑥ 必含检测：eval_required_headings.py 扫描并提取强制性 H2 标题
⑦ 模板提取：template_extractor.py 解析 Word 模板样式与段落规范
⑧ 片段预筛：检索片段库并经 relevance_check.py 过滤后预填大纲
⑨ 结构确认：输出 4 级大纲与 estimate_tokens.py 耗时报告，等待用户确认
⑩ 章节撰写：按大纲撰写各章节内容（结合图表要求展开）
⑪ 字数核验：check_chapter_words.py 校验各章节目标字数达标情况
⑫ 去 AI 痕迹：结合 references/de-ai-rules.md 消除机器感用语
⑬ 相关性验：校验内容与招标需求的契合度
⑭ 残留排查：snippet_adapt.py 确认无历史标书专有名词残留
⑮ 汇总转换：merge_chapters.py 合并，convert_to_word.py 渲染排版
⑯ 全量质检：doc_quality_check.py 执行最终完整性与格式闭环检查
⑰ 片段沉淀：snippet_manager.py 提取优质通用方案片段存入知识库
⑱ 交付通知：向用户汇报终稿成果与文件路径
```

---

## 5. 安全与脱敏声明

1. **零敏感凭据**：本便携包所有代码、配置及文档中均**不包含任何真实密钥、私有 Token、密码或云服务凭据**（如有敏感位已完成 `<REDACTED>` 脱敏处理）。
2. **零商业数据**：本包已彻底排查并剔除所有特定项目实际标书正文、客户商务数据与敏感工程样例，符合公开托管与安全合规标准。
3. **安全审计日志**：导出与审计日志保存在 `/workspace/mem/logs/export-bobobiaoshu-skill.log`。