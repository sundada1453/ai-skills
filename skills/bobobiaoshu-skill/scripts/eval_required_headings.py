#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
必含标题检测脚本 v1.0
扫描招标文件中「包括但不限于」「包括但不限于以下」「至少包含」等模式，
提取枚举项作为强制H2标题，检查大纲是否全覆盖。

功能:
  scan   - 扫描招标文件，提取所有「包括但不限于」必含标题
  check  - 对比大纲，检查必含标题是否全覆盖
  report - 一步到位：扫描 + 检查（推荐）

用法:
  python eval_required_headings.py scan <招标文件解析结果.md> [--output <输出.json>]
  python eval_required_headings.py check <必含标题.json> --outline <大纲.md>
  python eval_required_headings.py report <招标文件解析结果.md> --outline <大纲.md> [--output <输出目录>]

示例:
  # 一键扫描+检查
  python eval_required_headings.py report 招标文件_解析结果.md --outline 大纲.md --output 项目目录/

  # 仅扫描
  python eval_required_headings.py scan 招标文件_解析结果.md --output required_headings.json

  # 仅检查
  python eval_required_headings.py check required_headings.json --outline 大纲.md
"""

import sys
import os
import re
import json
from datetime import datetime


# ============================================================
# 「包括但不限于」模式提取
# ============================================================

# 触发关键词（按优先级排列）
TRIGGER_PATTERNS = [
    r'包括但不限于',
    r'包括但不限于以下',
    r'至少应?包括',
    r'至少包含',
    r'应当包括',
    r'应包含',
    r'主要内容应?包括',
    r'应覆盖以下',
    r'应涵盖',
]

# 枚举项分隔模式
# 1. 顿号/逗号分隔：满足程度、进度安排、实施人员安排
# 2. 编号列表：1. xxx 2. xxx / （1）xxx （2）xxx / ① xxx ② xxx
# 3. 换行分隔的列表项


def extract_enumerated_items(text, max_items=15):
    """从「包括但不限于」后的文本中提取枚举项

    支持三种格式：
    1. 顿号/逗号分隔的连续列表
    2. 编号列表（1. 2. / （1）（2） / ① ②）
    3. 换行分隔的短句列表
    """
    items = []

    # 尝试模式1：编号列表（最可靠）
    # 1. xxx 2. xxx 或 1、xxx 2、xxx
    numbered = re.findall(
        r'(?:^|\n)\s*(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*(.+?)(?=\n\s*(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])|\n\n|$)',
        text
    )
    if len(numbered) >= 2:
        for item in numbered:
            item = item.strip()
            # 清理尾部标点
            item = re.sub(r'[。；;，,]+$', '', item)
            if 2 <= len(item) <= 50:
                items.append(item)
        if items:
            return items

    # 尝试模式2：顿号/逗号分隔
    # 取包括但不限于后的第一段连续文本
    first_segment = text.split('\n')[0].strip() if text else ''
    # 去掉前导的冒号
    first_segment = re.sub(r'^[：:]\s*', '', first_segment)

    # 用顿号或逗号分割
    parts = re.split(r'[、，,；;]', first_segment)
    for part in parts:
        part = part.strip()
        # 去掉编号前缀
        part = re.sub(r'^(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*', '', part)
        # 去掉尾部标点和描述
        part = re.sub(r'[。.；;]+$', '', part)
        # 去掉「等方面」「等内容」等尾缀
        part = re.sub(r'(等方面|等内容|等环节|等部分|等要素)$', '', part)
        if 2 <= len(part) <= 50:
            items.append(part)

    if len(items) >= 2:
        return items

    # 尝试模式3：换行分隔的短句
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        # 去掉编号前缀
        line = re.sub(r'^(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+[、.）)])\s*', '', line)
        line = re.sub(r'[。.；;]+$', '', line)
        if 4 <= len(line) <= 50 and not line.startswith('包括'):
            items.append(line)

    return items[:max_items]


def scan_required_headings(tender_path):
    """扫描招标文件，提取所有「包括但不限于」必含标题

    返回结构:
    [
        {
            "chapter_hint": "工作进度及控制方案",
            "trigger_phrase": "包括但不限于",
            "raw_text": "...原始文本...",
            "required_items": ["满足程度", "进度安排", "实施人员安排"],
            "line_number": 2017
        },
        ...
    ]
    """
    with open(tender_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    results = []
    trigger_regex = '|'.join(TRIGGER_PATTERNS)

    for i, line in enumerate(lines):
        # 查找触发词
        match = re.search(trigger_regex, line)
        if not match:
            continue

        trigger_phrase = match.group()

        # 提取触发词后的文本（可能跨行）
        # 先取本行触发词之后的部分
        after_trigger = line[match.end():]

        # 如果本行触发词后内容太少，拼接后续行
        if len(after_trigger.strip()) < 5:
            # 向后扫描最多5行
            combined = after_trigger
            for j in range(1, 6):
                if i + j < len(lines):
                    combined += '\n' + lines[i + j]
            after_trigger = combined
        else:
            # 也拼接后续2行以捕获换行列表
            combined = after_trigger
            for j in range(1, 3):
                if i + j < len(lines):
                    next_line = lines[i + j].strip()
                    if next_line and not re.search(trigger_regex, next_line):
                        combined += '\n' + next_line
                    else:
                        break
            after_trigger = combined

        # 提取枚举项
        items = extract_enumerated_items(after_trigger)

        if len(items) < 2:
            continue

        # 尝试推断所属章节
        chapter_hint = _infer_chapter(line, lines, i)

        results.append({
            'chapter_hint': chapter_hint,
            'trigger_phrase': trigger_phrase,
            'raw_text': line.strip()[:200],
            'required_items': items,
            'line_number': i + 1,
        })

    # 去重：相同章节的相同项合并
    deduped = []
    seen = set()
    for r in results:
        key = (r['chapter_hint'], tuple(r['required_items']))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


def _infer_chapter(current_line, all_lines, line_idx):
    """根据上下文推断当前所属章节"""
    # 向上查找最近的标题行（## 或 ###）
    for j in range(line_idx, max(line_idx - 30, -1), -1):
        line = all_lines[j].strip()
        if line.startswith('## ') or line.startswith('### '):
            # 去掉 markdown 标记和编号
            title = re.sub(r'^#+\s*', '', line)
            title = re.sub(r'^\d+(?:\.\d+)*\s*', '', title)
            return title.strip()

    # 如果没找到标题，尝试从当前行提取章节名
    # 常见模式：xxx方案包括但不限于... / xxx应包括但不限于...
    m = re.match(r'(.{2,20})(?:方案|计划|措施|管理|制度|服务|内容|要求).*(?:包括但不限于|应包括|应包含)', current_line)
    if m:
        return m.group(1).strip() + '相关章节'

    return '未关联章节'


# ============================================================
# 大纲覆盖检查
# ============================================================

def check_outline_coverage(required_headings, outline_path):
    """检查大纲是否覆盖所有必含标题

    返回:
        results: 每个必含项的检查结果
        summary: 统计摘要
    """
    with open(outline_path, 'r', encoding='utf-8') as f:
        outline_content = f.read()

    # 提取大纲中的所有标题
    outline_headings = []
    for line in outline_content.split('\n'):
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            # 去掉编号前缀
            text = re.sub(r'^\d+(?:\.\d+)*\s*', '', text)
            text = re.sub(r'^[一二三四五六七八九十]+[、.]\s*', '', text)
            outline_headings.append((level, text))

    # 提取 H2 标题列表（必含项应在 H2 层级）
    h2_headings = [text for level, text in outline_headings if level == 2]

    results = []
    total_required = 0
    total_covered = 0
    total_missing = 0

    for group in required_headings:
        group_result = {
            'chapter_hint': group['chapter_hint'],
            'trigger_phrase': group['trigger_phrase'],
            'line_number': group['line_number'],
            'items': []
        }

        for item in group['required_items']:
            total_required += 1
            # 检查是否在大纲 H2 中出现（模糊匹配）
            found = False
            matched_heading = None
            for h2 in h2_headings:
                if item in h2 or h2 in item:
                    found = True
                    matched_heading = h2
                    break
                # 去掉常见后缀再比较
                item_clean = re.sub(r'(方案|措施|计划|管理|制度|内容|要求)$', '', item)
                h2_clean = re.sub(r'(方案|措施|计划|管理|制度|内容|要求)$', '', h2)
                if item_clean and h2_clean and (item_clean in h2_clean or h2_clean in item_clean):
                    found = True
                    matched_heading = h2
                    break

            if found:
                total_covered += 1
                status = '已覆盖'
            else:
                total_missing += 1
                status = '缺失'

            group_result['items'].append({
                'required_heading': item,
                'status': status,
                'matched_heading': matched_heading,
            })

        results.append(group_result)

    summary = {
        'total_required': total_required,
        'total_covered': total_covered,
        'total_missing': total_missing,
        'coverage_rate': f'{total_covered / total_required * 100:.1f}%' if total_required > 0 else 'N/A',
        'all_covered': total_missing == 0,
    }

    return results, summary


# ============================================================
# 报告生成
# ============================================================

def generate_report(results, summary, output_path=None):
    """生成 Markdown 格式的检查报告"""
    lines = []
    lines.append('# 必含标题覆盖检查报告')
    lines.append('')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    # 摘要
    lines.append('## 检查摘要')
    lines.append('')
    lines.append(f'| 指标 | 数值 |')
    lines.append(f'|------|------|')
    lines.append(f'| 必含标题总数 | {summary["total_required"]} |')
    lines.append(f'| 已覆盖 | {summary["total_covered"]} |')
    lines.append(f'| 缺失 | {summary["total_missing"]} |')
    lines.append(f'| 覆盖率 | {summary["coverage_rate"]} |')
    if summary['all_covered']:
        lines.append(f'| 总体结果 | ✅ 全部覆盖 |')
    else:
        lines.append(f'| 总体结果 | ❌ 存在缺失，需补充 |')
    lines.append('')

    # 详细结果
    lines.append('## 详细检查结果')
    lines.append('')

    for group in results:
        icon = '✅' if all(item['status'] == '已覆盖' for item in group['items']) else '❌'
        lines.append(f'### {icon} {group["chapter_hint"]}（第{group["line_number"]}行）')
        lines.append('')
        lines.append(f'触发词: `{group["trigger_phrase"]}`')
        lines.append('')

        lines.append('| 必含标题 | 状态 | 匹配的大纲标题 |')
        lines.append('|---------|------|---------------|')
        for item in group['items']:
            status_icon = '✅' if item['status'] == '已覆盖' else '❌'
            matched = item['matched_heading'] or '-'
            lines.append(f'| {item["required_heading"]} | {status_icon} {item["status"]} | {matched} |')
        lines.append('')

    # 缺失项汇总
    missing_items = []
    for group in results:
        for item in group['items']:
            if item['status'] == '缺失':
                missing_items.append({
                    'chapter': group['chapter_hint'],
                    'heading': item['required_heading'],
                    'line': group['line_number'],
                })

    if missing_items:
        lines.append('## 缺失标题汇总（需补充）')
        lines.append('')
        lines.append('以下标题在招标文件中被「包括但不限于」等措辞明确要求，')
        lines.append('但在当前大纲中未找到对应H2标题，必须补充：')
        lines.append('')
        lines.append('| 序号 | 所属章节 | 缺失的必含标题 | 招标文件行号 |')
        lines.append('|------|---------|--------------|------------|')
        for idx, m in enumerate(missing_items, 1):
            lines.append(f'| {idx} | {m["chapter"]} | **{m["heading"]}** | {m["line"]} |')
        lines.append('')
        lines.append('**处理建议：**')
        lines.append('- 在对应章节中新增H2标题（`## 标题名称`）')
        lines.append('- 如果已有类似标题，重命名以精确匹配')
        lines.append('- 每个必含标题下需编写实质性内容（不少于500字）')
        lines.append('')

    report = '\n'.join(lines)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f'报告已保存: {output_path}')

    return report


# ============================================================
# 主命令
# ============================================================

def cmd_scan(args):
    """扫描招标文件，提取必含标题"""
    tender_path = args[0]
    if not os.path.exists(tender_path):
        print(f'错误：文件不存在: {tender_path}')
        return 1

    output_path = None
    if '--output' in args:
        idx = args.index('--output')
        output_path = args[idx + 1]

    print(f'扫描招标文件: {tender_path}')
    results = scan_required_headings(tender_path)

    print(f'\n找到 {len(results)} 组「包括但不限于」必含标题:')
    total_items = 0
    for r in results:
        print(f'\n  [{r["chapter_hint"]}] (第{r["line_number"]}行)')
        print(f'  触发词: {r["trigger_phrase"]}')
        for item in r['required_items']:
            print(f'    - {item}')
            total_items += 1

    print(f'\n共 {total_items} 个必含标题项')

    json_data = json.dumps(results, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_data)
        print(f'JSON 已保存: {output_path}')
    else:
        print(f'\nJSON:\n{json_data}')

    return 0


def cmd_check(args):
    """检查大纲覆盖"""
    json_path = args[0]
    outline_path = None
    if '--outline' in args:
        idx = args.index('--outline')
        outline_path = args[idx + 1]

    if not outline_path:
        print('错误：需要 --outline 参数')
        return 1

    with open(json_path, 'r', encoding='utf-8') as f:
        required_headings = json.load(f)

    results, summary = check_outline_coverage(required_headings, outline_path)

    print(f'\n检查结果:')
    print(f'  必含标题: {summary["total_required"]}')
    print(f'  已覆盖: {summary["total_covered"]}')
    print(f'  缺失: {summary["total_missing"]}')
    print(f'  覆盖率: {summary["coverage_rate"]}')

    if summary['all_covered']:
        print('\n✅ 全部覆盖')
    else:
        print('\n❌ 存在缺失:')
        for group in results:
            for item in group['items']:
                if item['status'] == '缺失':
                    print(f'  - [{group["chapter_hint"]}] {item["required_heading"]}')

    return 0 if summary['all_covered'] else 1


def cmd_report(args):
    """一键扫描+检查+报告"""
    tender_path = args[0]
    outline_path = None
    output_dir = None

    if '--outline' in args:
        idx = args.index('--outline')
        outline_path = args[idx + 1]
    if '--output' in args:
        idx = args.index('--output')
        output_dir = args[idx + 1]

    if not os.path.exists(tender_path):
        print(f'错误：文件不存在: {tender_path}')
        return 1
    if not outline_path or not os.path.exists(outline_path):
        print(f'错误：大纲文件不存在: {outline_path}')
        return 1

    # Step 1: 扫描
    print('Step 1: 扫描招标文件中的「包括但不限于」模式...')
    required_headings = scan_required_headings(tender_path)
    total_items = sum(len(r['required_items']) for r in required_headings)
    print(f'  找到 {len(required_headings)} 组，共 {total_items} 个必含标题')

    # Step 2: 检查
    print('\nStep 2: 检查大纲覆盖...')
    results, summary = check_outline_coverage(required_headings, outline_path)
    print(f'  已覆盖: {summary["total_covered"]} / {summary["total_required"]}')
    print(f'  缺失: {summary["total_missing"]}')
    print(f'  覆盖率: {summary["coverage_rate"]}')

    # Step 3: 生成报告
    print('\nStep 3: 生成报告...')
    report_path = None
    json_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, '必含标题检查报告.md')
        json_path = os.path.join(output_dir, 'required_headings.json')

    report = generate_report(results, summary, report_path)

    if json_path:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(required_headings, f, ensure_ascii=False, indent=2)
        print(f'  JSON 已保存: {json_path}')

    print(f'\n{"✅" if summary["all_covered"] else "❌"} {"全部覆盖" if summary["all_covered"] else "存在缺失，请查看报告"}')

    return 0 if summary['all_covered'] else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == 'scan':
        sys.exit(cmd_scan(args))
    elif command == 'check':
        sys.exit(cmd_check(args))
    elif command == 'report':
        sys.exit(cmd_report(args))
    else:
        print(f'未知命令: {command}')
        print('可用命令: scan, check, report')
        sys.exit(1)


if __name__ == '__main__':
    main()
