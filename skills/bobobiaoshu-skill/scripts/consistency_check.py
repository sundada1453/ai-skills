#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节间一致性检查脚本 v1.0
检查标书文档中的跨章节矛盾、术语不统一、数值冲突等问题。

检查维度:
1. 术语统一性 — 同一概念在不同章节使用了不同写法
2. 数值一致性 — 同一指标在不同章节出现矛盾数值
3. 角色命名统一 — 项目负责人/项目经理等角色名全文统一
4. 禁用词检测 — 标书中不应出现的写法（7*24、我方等）
5. 首次缩写全称 — 缩写首次出现是否标注全称

用法:
    python consistency_check.py <文档.docx> [--vocabulary <术语库目录>]
    python consistency_check.py <文档.md>  [--vocabulary <术语库目录>]
"""

import sys
import os
import re
import json
from docx import Document


# ============================================================
# 术语库加载
# ============================================================

def load_vocabulary(vocab_dir):
    """从术语库目录加载术语规则

    解析 vocabulary/ 下的 .md 文件，提取:
    - 统一术语表（表格中的 "统一写法 | 禁止写法"）
    - 同义词组（说明含"全文统一"的行，仅提示统一，不报错）
    - 禁用词（说明含"禁止"的行，或内置禁用词）
    - 术语组（同一概念的不同写法视为一组）
    """
    if not vocab_dir or not os.path.isdir(vocab_dir):
        return [], [], [], []

    term_groups = []   # [(统一写法, [同义写法列表], is_banned), ...]
    banned = []        # [真正禁止的词, ...]
    synonyms = []      # [(统一写法, [同义写法]), ...]
    abbrev_rules = []  # [(缩写, 全称), ...]

    for fname in os.listdir(vocab_dir):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(vocab_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析表格行: | 统一写法 | 禁止写法 | 说明 |
        for line in content.split('\n'):
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if len(cells) < 3:
                continue
            # 跳过分隔行
            if all(set(c) <= set('- :') for c in cells):
                continue
            # 跳过表头
            if '统一写法' in cells[0]:
                continue

            canonical = cells[0]
            variant_str = cells[1] if len(cells) > 1 else ''
            note = cells[2] if len(cells) > 2 else ''

            if not variant_str or variant_str == canonical:
                continue

            variants = [v.strip() for v in variant_str.split('/') if v.strip()]

            # 判断是"全文统一"（同义词）还是"禁止"
            is_banned = '禁止' in note
            if is_banned:
                banned.extend(variants)
                term_groups.append((canonical, variants, True))
            else:
                synonyms.append((canonical, variants))
                term_groups.append((canonical, variants, False))

        # 解析缩写规则
        for line in content.split('\n'):
            m = re.search(r'([A-Z]{2,})\s*[（(]([^）)]+)[）)]\s*.*?首次出现', line)
            if m:
                abbrev_rules.append((m.group(1), m.group(2)))

    return term_groups, banned, synonyms, abbrev_rules


# ============================================================
# 内置一致性规则（不依赖术语库也能工作）
# ============================================================

BUILTIN_TERM_GROUPS = [
    # (统一写法, [禁止写法])
    # 注意: 禁止写法只填真正错误/不规范的变体，不填不同表述的同义词
    # 同义词由术语统一性检查自动处理（多个变体同时出现时提示统一）
    ('7×24小时', ['7*24', '7x24', '7X24', '7Ｘ24']),
    ('5×8小时', ['5*8', '5x8', '5X8']),
    ('项目组', ['我方', '我们']),
    ('等级保护', ['等保2.0', '等保3.0']),
    ('信息系统', ['IT系统', 'it系统']),
]

BUILTIN_BANNED = [
    # 真正禁止的写法（不是同义词，是错误/不规范写法）
    '我方', '我们', '我司',
    '7*24', '7x24', '5*8', '5x8',
    '本章小结', '本章总结',
    '标志着', '见证了', '彰显了',
]

BUILTIN_ABBREV_RULES = [
    ('SLA', '服务级别协议'),
    ('PMO', '项目管理办公室'),
    ('ETC', '电子不停车收费系统'),
    ('CMMI', '能力成熟度模型集成'),
    ('WBS', '工作分解结构'),
    ('PDCA', '计划-执行-检查-处理'),
]


# ============================================================
# 文档文本提取
# ============================================================

def extract_text_from_docx(docx_path):
    """从 Word 文档提取文本，按段落"""
    doc = Document(docx_path)
    paragraphs = []
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip():
            style = para.style.name if para.style else ''
            paragraphs.append({
                'idx': i,
                'text': para.text,
                'style': style,
                'is_heading': style.startswith('Heading') if style else False,
            })
    return paragraphs


def extract_text_from_md(md_path):
    """从 Markdown 提取文本"""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    paragraphs = []
    for i, line in enumerate(content.split('\n')):
        if line.strip():
            is_heading = line.startswith('#')
            paragraphs.append({
                'idx': i,
                'text': line,
                'style': 'Heading' if is_heading else 'Normal',
                'is_heading': is_heading,
            })
    return paragraphs


# ============================================================
# 检查函数
# ============================================================

def check_term_consistency(paragraphs, term_groups):
    """检查术语统一性：同一概念的不同写法出现在不同段落

    Args:
        term_groups: [(统一写法, [变体列表], is_banned), ...]
    """
    issues = []

    # 建立: 写法 -> 出现位置列表
    term_occurrences = {}
    for canonical, variants, is_banned in term_groups:
        all_variants = [canonical] + variants
        for variant in all_variants:
            if variant not in term_occurrences:
                term_occurrences[variant] = []
            for p in paragraphs:
                if variant in p['text']:
                    term_occurrences[variant].append((p['idx'], p['text'][:60]))

    # 检查: 如果同一术语组内多个变体都有出现
    seen_issues = set()
    for canonical, variants, is_banned in term_groups:
        all_variants = [canonical] + variants
        found_variants = []
        for variant in all_variants:
            if term_occurrences.get(variant):
                found_variants.append((variant, len(term_occurrences[variant])))

        if len(found_variants) > 1:
            # 用规范写法+变体集合做去重key
            key = (canonical, tuple(sorted([v for v, _ in found_variants])))
            if key in seen_issues:
                continue
            seen_issues.add(key)

            # 多个变体同时出现
            detail_parts = []
            for variant, count in found_variants:
                first_loc = term_occurrences[variant][0]
                detail_parts.append(f'"{variant}"出现{count}次(段落{first_loc[0]})')

            severity = 'error' if is_banned else 'warning'
            label = '禁用词混用' if is_banned else '术语不统一'
            issues.append({
                'type': label,
                'severity': severity,
                'detail': f'{", ".join(detail_parts)}，建议统一为"{canonical}"',
                'locations': [v[0] for v in found_variants],
            })

    return issues


def check_banned_terms(paragraphs, banned):
    """检查禁用词（仅检查真正禁止的词，同义词由术语统一性检查处理）"""
    issues = []
    for p in paragraphs:
        for term in banned:
            # 精确匹配，避免"项目经理"误报为包含"项目"的问题
            if term in p['text']:
                issues.append({
                    'type': '禁用词',
                    'severity': 'error',
                    'detail': f'段落{p["idx"]}: 发现禁用词"{term}"',
                    'text': p['text'][:60],
                    'term': term,
                })
    return issues


def check_numeric_consistency(paragraphs):
    """检查数值一致性：同一指标在不同段落的数值是否矛盾"""
    issues = []

    # 提取模式: "XX人" "XX天" "XX小时" "XX万元" "XX台" "XX套" "XX个"
    # 按 指标关键词+单位 分组
    numeric_pattern = re.compile(
        r'(\d+(?:\.\d+)?)\s*'  # 数值
        r'(人|天|小时|个工作日|周|月|年|万元|元|台|套|个|项|次|页|%|百分比)',
    )

    # 提取上下文关键词（数值前3-10字）
    def get_context(text, pos):
        start = max(0, pos - 10)
        ctx = text[start:pos].strip()
        # 去掉纯数字和标点
        ctx = re.sub(r'[\d,，.、]+$', '', ctx)
        return ctx

    # 按(上下文关键词+单位)分组
    value_groups = {}
    for p in paragraphs:
        for m in numeric_pattern.finditer(p['text']):
            value = m.group(1)
            unit = m.group(2)
            pos = m.start()
            ctx = get_context(p['text'], pos)
            key = f'{ctx}{unit}'

            if key not in value_groups:
                value_groups[key] = []
            value_groups[key].append({
                'value': value,
                'unit': unit,
                'para_idx': p['idx'],
                'text': p['text'][:60],
                'context': ctx,
            })

    # 检查同一key下不同值
    for key, entries in value_groups.items():
        values = set(e['value'] for e in entries)
        if len(values) > 1 and len(entries) > 1:
            # 只报告有意义的冲突（排除明显不同的上下文）
            issues.append({
                'type': '数值冲突',
                'severity': 'warning',
                'detail': f'"{key}" 出现不同数值: ' + ' | '.join(
                    [f'{e["value"]}{e["unit"]}(段落{e["para_idx"]})' for e in entries]
                ),
                'locations': [e['para_idx'] for e in entries],
            })

    return issues


def check_role_consistency(paragraphs):
    """检查角色命名全文统一"""
    issues = []

    role_groups = [
        (['项目负责人', '项目经理', '项目总监'], '项目负责角色'),
        (['技术负责人', '技术总监', '技术经理'], '技术负责角色'),
        (['质量负责人', '质量经理'], '质量负责角色'),
        (['安全负责人', '安全管理员', '安全经理'], '安全负责角色'),
        (['驻场服务', '驻场支持'], '驻场服务'),
    ]

    for variants, label in role_groups:
        found = {}
        for variant in variants:
            for p in paragraphs:
                if variant in p['text']:
                    if variant not in found:
                        found[variant] = []
                    found[variant].append(p['idx'])

        if len(found) > 1:
            parts = [f'"{v}"出现在段落{locs[0]}' for v, locs in found.items()]
            issues.append({
                'type': '角色命名不统一',
                'severity': 'warning',
                'detail': f'{label}: {", ".join(parts)}，建议全文统一为"{variants[0]}"',
            })

    return issues


def check_abbreviation_first_use(paragraphs, abbrev_rules):
    """检查缩写首次出现是否标注全称"""
    issues = []

    for abbrev, full_name in abbrev_rules:
        first_para = None
        has_full_form = False

        for p in paragraphs:
            if abbrev in p['text']:
                if first_para is None:
                    first_para = p['idx']
                    # 检查首次出现是否包含全称
                    if full_name in p['text'] or f'{abbrev}（{full_name}' in p['text'] or f'{abbrev}({full_name}' in p['text']:
                        has_full_form = True

        if first_para is not None and not has_full_form:
            issues.append({
                'type': '缩写无全称',
                'severity': 'warning',
                'detail': f'段落{first_para}: "{abbrev}"首次出现未标注全称"{full_name}"',
            })

    return issues


# ============================================================
# 主函数
# ============================================================

def run_consistency_check(input_path, vocab_dir=None):
    """执行一致性检查"""
    print(f'检查文档: {input_path}')
    if vocab_dir:
        print(f'术语库: {vocab_dir}')
    print()

    # 提取文本
    ext = os.path.splitext(input_path)[1].lower()
    if ext == '.docx':
        paragraphs = extract_text_from_docx(input_path)
    elif ext in ('.md', '.txt'):
        paragraphs = extract_text_from_md(input_path)
    else:
        print(f'不支持的格式: {ext}')
        return []

    # 加载术语库
    vocab_groups, vocab_banned, vocab_synonyms, vocab_abbrevs = load_vocabulary(vocab_dir)

    # 合并内置规则和术语库规则
    # 内置 term_groups 格式: (统一写法, [禁止写法]) → 转换为 (统一写法, [变体], is_banned)
    all_groups = [(c, v, False) for c, v in BUILTIN_TERM_GROUPS] + vocab_groups
    all_banned = list(set(BUILTIN_BANNED + vocab_banned))
    all_synonyms = vocab_synonyms  # 同义词组用于统一性检查
    all_abbrevs = BUILTIN_ABBREV_RULES + vocab_abbrevs

    all_issues = []

    # 1. 术语统一性
    print('--- 1. 术语统一性检查 ---')
    term_issues = check_term_consistency(paragraphs, all_groups)
    all_issues.extend(term_issues)
    print(f'  发现 {len(term_issues)} 个问题')

    # 2. 禁用词
    print('--- 2. 禁用词检查 ---')
    banned_issues = check_banned_terms(paragraphs, all_banned)
    all_issues.extend(banned_issues)
    print(f'  发现 {len(banned_issues)} 个问题')

    # 3. 数值一致性
    print('--- 3. 数值一致性检查 ---')
    numeric_issues = check_numeric_consistency(paragraphs)
    all_issues.extend(numeric_issues)
    print(f'  发现 {len(numeric_issues)} 个问题')

    # 4. 角色命名统一
    print('--- 4. 角色命名统一检查 ---')
    role_issues = check_role_consistency(paragraphs)
    all_issues.extend(role_issues)
    print(f'  发现 {len(role_issues)} 个问题')

    # 5. 缩写首次全称
    print('--- 5. 缩写首次全称检查 ---')
    abbrev_issues = check_abbreviation_first_use(paragraphs, all_abbrevs)
    all_issues.extend(abbrev_issues)
    print(f'  发现 {len(abbrev_issues)} 个问题')

    # 汇总
    print()
    print('=' * 60)
    errors = [i for i in all_issues if i.get('severity') == 'error']
    warnings = [i for i in all_issues if i.get('severity') == 'warning']
    print(f'检查结果: {len(errors)} 个错误, {len(warnings)} 个警告')

    if all_issues:
        print()
        for issue in errors + warnings:
            icon = '✗' if issue['severity'] == 'error' else '⚠'
            print(f'  {icon} [{issue["type"]}] {issue["detail"]}')
    else:
        print('  全部通过！')

    return all_issues


def main():
    if len(sys.argv) < 2:
        print('用法: python consistency_check.py <文档.docx|.md> [--vocabulary <术语库目录>]')
        print()
        print('检查维度:')
        print('  1. 术语统一性 — 同一概念不同写法')
        print('  2. 禁用词 — 标书中不应出现的写法')
        print('  3. 数值一致性 — 同一指标矛盾数值')
        print('  4. 角色命名统一 — 项目负责人/项目经理等')
        print('  5. 缩写首次全称 — SLA/PMO等首次出现是否标注')
        sys.exit(1)

    input_path = sys.argv[1]
    vocab_dir = None

    # 默认术语库路径
    default_vocab = os.path.join(os.path.expanduser('~'), 'Desktop', '2026招投标', 'memory', 'vocabulary')

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--vocabulary' and i + 1 < len(args):
            vocab_dir = args[i + 1]
            i += 2
        else:
            i += 1

    # 如果未指定术语库，使用默认路径
    if vocab_dir is None and os.path.isdir(default_vocab):
        vocab_dir = default_vocab

    issues = run_consistency_check(input_path, vocab_dir)
    sys.exit(0 if not issues else 1)


if __name__ == '__main__':
    main()
