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
"""

import sys
import os
import re
import json
from datetime import datetime

TRIGGER_PATTERNS = [r'包括但不限于', r'包括但不限于以下', r'至少应?包括', r'至少包含', r'应当包括', r'应包含', r'主要内容应?包括', r'应覆盖以下', r'应涵盖']


def extract_enumerated_items(text, max_items=15):
    """从「包括但不限于」后的文本中提取枚举项"""
    items = []
    numbered = re.findall(r'(?:^|\n)\s*(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*(.+?)(?=\n\s*(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])|\n\n|$)', text)
    if len(numbered) >= 2:
        for item in numbered:
            item = re.sub(r'[。；;，,]+$', '', item.strip())
            if 2 <= len(item) <= 50: items.append(item)
        if items: return items
    first_segment = text.split('\n')[0].strip() if text else ''
    first_segment = re.sub(r'^[：:]\s*', '', first_segment)
    parts = re.split(r'[、，,；;]', first_segment)
    for part in parts:
        part = re.sub(r'^(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩])\s*', '', part.strip())
        part = re.sub(r'[。.；;]+$', '', part)
        part = re.sub(r'(等方面|等内容|等环节|等部分|等要素)$', '', part)
        if 2 <= len(part) <= 50: items.append(part)
    if len(items) >= 2: return items
    for line in text.strip().split('\n'):
        line = re.sub(r'^(?:\d+[.、）)]|[（(]\d+[）)]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+[、.）)])\s*', '', line.strip())
        line = re.sub(r'[。.；;]+$', '', line)
        if 4 <= len(line) <= 50 and not line.startswith('包括'): items.append(line)
    return items[:max_items]


def scan_required_headings(tender_path):
    """扫描招标文件，提取所有必含标题"""
    with open(tender_path, 'r', encoding='utf-8') as f: lines = f.readlines()
    results = []
    trigger_regex = '|'.join(TRIGGER_PATTERNS)
    for i, line in enumerate(lines):
        match = re.search(trigger_regex, line)
        if not match: continue
        trigger_phrase = match.group()
        after_trigger = line[match.end():]
        if len(after_trigger.strip()) < 5:
            combined = after_trigger
            for j in range(1, 6):
                if i + j < len(lines): combined += '\n' + lines[i + j]
            after_trigger = combined
        else:
            combined = after_trigger
            for j in range(1, 3):
                if i + j < len(lines):
                    next_line = lines[i + j].strip()
                    if next_line and not re.search(trigger_regex, next_line): combined += '\n' + next_line
                    else: break
            after_trigger = combined
        items = extract_enumerated_items(after_trigger)
        if len(items) < 2: continue
        chapter_hint = _infer_chapter(line, lines, i)
        results.append({'chapter_hint': chapter_hint, 'trigger_phrase': trigger_phrase, 'raw_text': line.strip()[:200], 'required_items': items, 'line_number': i + 1})
    deduped, seen = [], set()
    for r in results:
        key = (r['chapter_hint'], tuple(r['required_items']))
        if key not in seen: seen.add(key); deduped.append(r)
    return deduped


def _infer_chapter(current_line, all_lines, line_idx):
    """根据上下文推断当前所属章节"""
    for j in range(line_idx, max(line_idx - 30, -1), -1):
        line = all_lines[j].strip()
        if line.startswith('## ') or line.startswith('### '):
            title = re.sub(r'^#+\s*', '', line)
            title = re.sub(r'^\d+(?:\.\d+)*\s*', '', title)
            return title.strip()
    m = re.match(r'(.{2,20})(?:方案|计划|措施|管理|制度|服务|内容|要求).*(?:包括但不限于|应包括|应包含)', current_line)
    return m.group(1).strip() + '相关章节' if m else '未关联章节'


def check_outline_coverage(required_headings, outline_path):
    """检查大纲是否覆盖所有必含标题"""
    with open(outline_path, 'r', encoding='utf-8') as f: outline_content = f.read()
    outline_headings = []
    for line in outline_content.split('\n'):
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            text = re.sub(r'^[一二三四五六七八九十]+[、.]\s*', '', re.sub(r'^\d+(?:\.\d+)*\s*', '', m.group(2).strip()))
            outline_headings.append((len(m.group(1)), text))
    h2_headings = [text for level, text in outline_headings if level == 2]
    results, total_required, total_covered, total_missing = [], 0, 0, 0
    for group in required_headings:
        group_result = {'chapter_hint': group['chapter_hint'], 'trigger_phrase': group['trigger_phrase'], 'line_number': group['line_number'], 'items': []}
        for item in group['required_items']:
            total_required += 1; found = False; matched_heading = None
            for h2 in h2_headings:
                item_clean = re.sub(r'(方案|措施|计划|管理|制度|内容|要求)$', '', item)
                h2_clean = re.sub(r'(方案|措施|计划|管理|制度|内容|要求)$', '', h2)
                if item in h2 or h2 in item or (item_clean and h2_clean and (item_clean in h2_clean or h2_clean in item_clean)):
                    found = True; matched_heading = h2; break
            if found: total_covered += 1; status = '已覆盖'
            else: total_missing += 1; status = '缺失'
            group_result['items'].append({'required_heading': item, 'status': status, 'matched_heading': matched_heading})
        results.append(group_result)
    summary = {'total_required': total_required, 'total_covered': total_covered, 'total_missing': total_missing, 'coverage_rate': f'{total_covered / total_required * 100:.1f}%' if total_required > 0 else 'N/A', 'all_covered': total_missing == 0}
    return results, summary


def generate_report(results, summary, output_path=None):
    """生成 Markdown 格式的检查报告"""
    lines = ['# 必含标题覆盖检查报告', '', f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', '', '## 检查摘要', '', '| 指标 | 数值 |', '|------|------|', f'| 必含标题总数 | {summary["total_required"]} |', f'| 已覆盖 | {summary["total_covered"]} |', f'| 缺失 | {summary["total_missing"]} |', f'| 覆盖率 | {summary["coverage_rate"]} |']
    lines.append(f'| 总体结果 | {"✅ 全部覆盖" if summary["all_covered"] else "❌ 存在缺失，需补充"} |'); lines += ['', '## 详细检查结果', '']
    for group in results:
        icon = '✅' if all(item['status'] == '已覆盖' for item in group['items']) else '❌'
        lines += [f'### {icon} {group["chapter_hint"]}（第{group["line_number"]}行）', '', f'触发词: `{group["trigger_phrase"]}`', '', '| 必含标题 | 状态 | 匹配的大纲标题 |', '|---------|------|---------------|']
        for item in group['items']: lines.append(f'| {item["required_heading"]} | {"✅" if item["status"] == "已覆盖" else "❌"} {item["status"]} | {item["matched_heading"] or "-"} |')
        lines.append('')
    missing_items = [{'chapter': g['chapter_hint'], 'heading': i['required_heading'], 'line': g['line_number']} for g in results for i in g['items'] if i['status'] == '缺失']
    if missing_items:
        lines += ['## 缺失标题汇总（需补充）', '', '以下标题在招标文件中被「包括但不限于」等措辞明确要求，', '但在当前大纲中未找到对应H2标题，必须补充：', '', '| 序号 | 所属章节 | 缺失的必含标题 | 招标文件行号 |', '|------|---------|--------------|------------|']
        for idx, m in enumerate(missing_items, 1): lines.append(f'| {idx} | {m["chapter"]} | **{m["heading"]}** | {m["line"]} |')
        lines += ['', '**处理建议：**', '- 在对应章节中新增H2标题（`## 标题名称`）', '- 如果已有类似标题，重命名以精确匹配', '- 每个必含标题下需编写实质性内容（不少于500字）', '']
    report = '\n'.join(lines)
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f: f.write(report)
        print(f'报告已保存: {output_path}')
    return report


def cmd_scan(args):
    tender_path = args[0]
    if not os.path.exists(tender_path): print(f'错误：文件不存在: {tender_path}'); return 1
    output_path = args[args.index('--output') + 1] if '--output' in args else None
    print(f'扫描招标文件: {tender_path}'); results = scan_required_headings(tender_path)
    print(f'\n找到 {len(results)} 组「包括但不限于」必含标题:')
    total_items = 0
    for r in results:
        print(f'\n  [{r["chapter_hint"]}] (第{r["line_number"]}行)'); print(f'  触发词: {r["trigger_phrase"]}')
        for item in r['required_items']: print(f'    - {item}'); total_items += 1
    print(f'\n共 {total_items} 个必含标题项'); json_data = json.dumps(results, ensure_ascii=False, indent=2)
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f: f.write(json_data)
        print(f'JSON 已保存: {output_path}')
    else: print(f'\nJSON:\n{json_data}')
    return 0


def cmd_check(args):
    json_path = args[0]; outline_path = args[args.index('--outline') + 1] if '--outline' in args else None
    if not outline_path: print('错误：需要 --outline 参数'); return 1
    with open(json_path, 'r', encoding='utf-8') as f: required_headings = json.load(f)
    results, summary = check_outline_coverage(required_headings, outline_path)
    print(f'\n检查结果:\n  必含标题: {summary["total_required"]}\n  已覆盖: {summary["total_covered"]}\n  缺失: {summary["total_missing"]}\n  覆盖率: {summary["coverage_rate"]}')
    if summary['all_covered']: print('\n✅ 全部覆盖')
    else:
        print('\n❌ 存在缺失:')
        for group in results:
            for item in group['items']:
                if item['status'] == '缺失': print(f'  - [{group["chapter_hint"]}] {item["required_heading"]}')
    return 0 if summary['all_covered'] else 1


def cmd_report(args):
    tender_path = args[0]; outline_path = args[args.index('--outline') + 1] if '--outline' in args else None; output_dir = args[args.index('--output') + 1] if '--output' in args else None
    if not os.path.exists(tender_path): print(f'错误：文件不存在: {tender_path}'); return 1
    if not outline_path or not os.path.exists(outline_path): print(f'错误：大纲文件不存在: {outline_path}'); return 1
    print('Step 1: 扫描招标文件中的「包括但不限于」模式...'); required_headings = scan_required_headings(tender_path); total_items = sum(len(r['required_items']) for r in required_headings); print(f'  找到 {len(required_headings)} 组，共 {total_items} 个必含标题')
    print('\nStep 2: 检查大纲覆盖...'); results, summary = check_outline_coverage(required_headings, outline_path); print(f'  已覆盖: {summary["total_covered"]} / {summary["total_required"]}'); print(f'  缺失: {summary["total_missing"]}'); print(f'  覆盖率: {summary["coverage_rate"]}')
    print('\nStep 3: 生成报告...'); report_path = json_path = None
    if output_dir:
        os.makedirs(output_dir, exist_ok=True); report_path = os.path.join(output_dir, '必含标题检查报告.md'); json_path = os.path.join(output_dir, 'required_headings.json')
    generate_report(results, summary, report_path)
    if json_path:
        with open(json_path, 'w', encoding='utf-8') as f: json.dump(required_headings, f, ensure_ascii=False, indent=2)
        print(f'  JSON 已保存: {json_path}')
    print(f'\n{"✅" if summary["all_covered"] else "❌"} {"全部覆盖" if summary["all_covered"] else "存在缺失，请查看报告"}')
    return 0 if summary['all_covered'] else 1


def main():
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    command, args = sys.argv[1], sys.argv[2:]
    if command == 'scan': sys.exit(cmd_scan(args))
    elif command == 'check': sys.exit(cmd_check(args))
    elif command == 'report': sys.exit(cmd_report(args))
    else: print(f'未知命令: {command}'); print('可用命令: scan, check, report'); sys.exit(1)


if __name__ == '__main__':
    main()
