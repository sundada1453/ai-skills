#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token/时间估算脚本 v1.1
根据大纲结构和目标页数，估算编写标书所需的 token 消耗和时间。

功能:
  estimate - 解析大纲，结合评分分值和目标页数，输出估算报告

用法:
  python estimate_tokens.py estimate <大纲.md> --pages <目标页数> [--eval <eval_criteria.json>] [--with-tables] [--output <输出.md>]
  python estimate_tokens.py estimate <大纲.md> --pages 200 --eval eval_criteria.json --with-tables --output 估算报告.md

估算模型:
  - 每页约780中文字符
  - 中文 token 比率：1字 ≈ 1.3 token（输出）；1字 ≈ 1.5 token（输入含上下文）
  - 每章输入 token：招标文件上下文(~3000) + 大纲指令(~1000) + 片段内容(~2000, 如有)
  - 每章输出 token：字数 / 1.3（添加表格图表时 / 1.5）
  - 编写速度：Agent 模型约 600 字/分钟（并发时取最大单章时间）
  - 去 AI 痕迹：原文字数 × 0.3（额外 token）
  - 质量检查：固定 ~2000 token
  - 表格图表模式：输出 token 系数 1.3→1.5, 输入 token +5%, 模拟表格图表内容的额外 token 开销
"""

import sys
import os
import re
import json
import math
from datetime import datetime, timedelta


# ============================================================
# 常量
# ============================================================

CHARS_PER_PAGE = 780           # 每页中文字符数
OUTPUT_TOKEN_RATIO = 1.3       # 输出：1字 ≈ 1.3 token
OUTPUT_TOKEN_RATIO_TABLES = 1.5 # 输出（含表格图表）：1字 ≈ 1.5 token
INPUT_TOKEN_RATIO = 1.5        # 输入：1字 ≈ 1.5 token
WRITING_SPEED_CPM = 600        # Agent 编写速度：字/分钟
CONTEXT_TOKENS_PER_CHAPTER = 6000  # 每章输入上下文 token（招标文件+大纲+片段）
CONTEXT_TOKENS_TABLES_BONUS = 0.05 # 表格图表模式下输入 token 额外系数
DEAI_TOKEN_RATIO = 0.3         # 去 AI 痕迹额外 token = 原文 × 0.3
QA_TOKENS = 2000               # 质量检查固定 token
MERGE_TOKENS = 3000            # 合并+Word 生成固定 token
CONCURRENT_BATCHES = 4         # 并发批次（同时编写章节数）


# ============================================================
# 大纲解析
# ============================================================

def parse_outline(outline_path):
    """解析大纲文件，提取章节结构

    返回: [(level, title, children_count), ...]
    """
    with open(outline_path, 'r', encoding='utf-8') as f:
        content = f.read()

    chapters = []
    current_h1 = None
    current_h2_count = 0
    current_h3_count = 0

    for line in content.split('\n'):
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not m:
            continue

        level = len(m.group(1))
        title = m.group(2).strip()
        # 去掉编号前缀
        title = re.sub(r'^\d+(?:\.\d+)*\s*', '', title)
        title = re.sub(r'^[一二三四五六七八九十]+[、.]\s*', '', title)

        if level == 1:
            # 保存前一章
            if current_h1:
                chapters.append({
                    'title': current_h1['title'],
                    'h2_count': current_h2_count,
                    'h3_count': current_h3_count,
                })
            current_h1 = {'title': title}
            current_h2_count = 0
            current_h3_count = 0
        elif level == 2:
            current_h2_count += 1
        elif level == 3:
            current_h3_count += 1

    # 保存最后一章
    if current_h1:
        chapters.append({
            'title': current_h1['title'],
            'h2_count': current_h2_count,
            'h3_count': current_h3_count,
        })

    return chapters


def load_eval_scores(eval_path):
    """加载评分标准，获取各章分值"""
    if not eval_path or not os.path.exists(eval_path):
        return None

    with open(eval_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 尝试从评分项中匹配章节标题
    scores = {}
    items = data.get('items', data.get('eval_items', []))
    total_score = data.get('total_score', 100)

    for item in items:
        factor = item.get('factor', item.get('评分因素', ''))
        score = item.get('score', item.get('分值', 0))
        category = item.get('category', item.get('类别', ''))

        # 跳过价格类
        if category == '价格' or '报价' in factor or '价格' in factor:
            continue

        scores[factor] = float(score) if score else 0

    return {'total_score': total_score, 'items': scores}


def match_chapter_score(chapter_title, eval_data):
    """模糊匹配章节标题到评分项"""
    if not eval_data:
        return None

    for factor, score in eval_data['items'].items():
        # 精确匹配
        if factor in chapter_title or chapter_title in factor:
            return score
        # 去后缀匹配
        clean_factor = re.sub(r'(方案|计划|措施|管理|制度|内容|要求|服务)$', '', factor)
        clean_title = re.sub(r'(方案|计划|措施|管理|制度|内容|要求|服务)$', '', chapter_title)
        if clean_factor and clean_title and (clean_factor in clean_title or clean_title in clean_factor):
            return score

    return None


# ============================================================
# 估算逻辑
# ============================================================

def estimate(chapters, target_pages, eval_data=None, with_tables=False):
    """估算 token 消耗和时间

    返回: (chapter_estimates, total_summary)
    """
    total_chars = target_pages * CHARS_PER_PAGE
    total_score = eval_data['total_score'] if eval_data else 100

    # 表格图表模式：输出 token 系数调整
    output_ratio = OUTPUT_TOKEN_RATIO_TABLES if with_tables else OUTPUT_TOKEN_RATIO
    # 表格图表模式：输入 token 额外系数
    context_bonus = 1 + CONTEXT_TOKENS_TABLES_BONUS if with_tables else 1.0

    # 计算各章字数分配
    chapter_estimates = []
    total_assigned_chars = 0
    unscored_chapters = []

    for ch in chapters:
        score = match_chapter_score(ch['title'], eval_data) if eval_data else None

        if score and score > 0:
            # 按分值分配
            chars = int(score / total_score * total_chars)
        else:
            # 无分值的章节，稍后平均分配
            chars = None
            unscored_chapters.append(ch['title'])

        # 复杂度因子：H2+H3 越多，上下文 token 越多
        complexity = 1 + (ch['h2_count'] + ch['h3_count']) * 0.05

        chapter_estimates.append({
            'title': ch['title'],
            'h2_count': ch['h2_count'],
            'h3_count': ch['h3_count'],
            'score': score,
            'target_chars': chars,
            'complexity': complexity,
        })

        if chars:
            total_assigned_chars += chars

    # 将剩余字数分配给无分值章节
    remaining_chars = total_chars - total_assigned_chars
    if unscored_chapters and remaining_chars > 0:
        per_chapter = remaining_chars // len(unscored_chapters)
        for est in chapter_estimates:
            if est['target_chars'] is None:
                est['target_chars'] = per_chapter

    # 计算 token 和时间
    total_input_tokens = 0
    total_output_tokens = 0
    total_deai_tokens = 0
    max_chapter_time = 0
    total_serial_time = 0

    for est in chapter_estimates:
        chars = est['target_chars'] or 5000

        # 输入 token：上下文 + 指令（表格图表模式下额外增加）
        input_tokens = int(CONTEXT_TOKENS_PER_CHAPTER * est['complexity'] * context_bonus)
        # 输出 token：正文字数（表格图表模式下系数更高）
        output_tokens = int(chars * output_ratio)
        # 去 AI 痕迹 token
        deai_tokens = int(chars * DEAI_TOKEN_RATIO)

        # 编写时间（分钟）
        write_time = chars / WRITING_SPEED_CPM
        # 去 AI 痕迹时间
        deai_time = write_time * 0.3

        est['input_tokens'] = input_tokens
        est['output_tokens'] = output_tokens
        est['deai_tokens'] = deai_tokens
        est['total_tokens'] = input_tokens + output_tokens + deai_tokens
        est['write_time_min'] = write_time
        est['deai_time_min'] = deai_time
        est['total_time_min'] = write_time + deai_time

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_deai_tokens += deai_tokens

        # 并发时间：取最大单章时间
        if est['total_time_min'] > max_chapter_time:
            max_chapter_time = est['total_time_min']
        total_serial_time += est['total_time_min']

    # 并发策略：按 CONCURRENT_BATCHES 分批
    # 排序按字数降序，大章先写
    sorted_times = sorted([e['total_time_min'] for e in chapter_estimates], reverse=True)
    batch_times = [0] * CONCURRENT_BATCHES
    for t in sorted_times:
        min_batch = batch_times.index(min(batch_times))
        batch_times[min_batch] += t
    concurrent_time = max(batch_times) if batch_times else 0

    # 加上固定开销
    qa_time = 3  # 质量检查约3分钟
    merge_time = 5  # 合并+Word生成约5分钟

    total_time_concurrent = concurrent_time + qa_time + merge_time
    total_time_serial = total_serial_time + qa_time + merge_time

    summary = {
        'target_pages': target_pages,
        'total_chars': total_chars,
        'chapter_count': len(chapters),
        'with_tables': with_tables,
        'total_input_tokens': total_input_tokens,
        'total_output_tokens': total_output_tokens,
        'total_deai_tokens': total_deai_tokens,
        'total_tokens': total_input_tokens + total_output_tokens + total_deai_tokens + QA_TOKENS + MERGE_TOKENS,
        'qa_tokens': QA_TOKENS,
        'merge_tokens': MERGE_TOKENS,
        'concurrent_time_min': total_time_concurrent,
        'serial_time_min': total_time_serial,
        'concurrent_time_str': _format_time(total_time_concurrent),
        'serial_time_str': _format_time(total_time_serial),
        'concurrent_batches': CONCURRENT_BATCHES,
    }

    return chapter_estimates, summary


def _format_time(minutes):
    """格式化时间"""
    if minutes < 60:
        return f'{minutes:.0f}分钟'
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f'{hours}小时{mins}分钟'


# ============================================================
# 报告生成
# ============================================================

def generate_report(chapter_estimates, summary, output_path=None):
    """生成 Markdown 格式的估算报告"""
    lines = []
    lines.append('# 标书编写 Token / 时间估算报告')
    lines.append('')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('')

    # 总览
    lines.append('## 总览')
    lines.append('')
    lines.append('| 指标 | 数值 |')
    lines.append('|------|------|')
    lines.append(f'| 目标页数 | {summary["target_pages"]} 页 |')
    lines.append(f'| 目标字数 | {summary["total_chars"]:,} 字 |')
    lines.append(f'| 章节数 | {summary["chapter_count"]} |')
    lines.append(f'| 并发批次 | {summary["concurrent_batches"]} 章同时编写 |')
    lines.append(f'| 表格图表 | {"✅ 添加（token +15%）" if summary.get("with_tables") else "❌ 不添加"} |')
    lines.append('')
    lines.append('### Token 估算')
    lines.append('')
    lines.append('| 类别 | Token 数 | 说明 |')
    lines.append('|------|----------|------|')
    lines.append(f'| 输入 token | {summary["total_input_tokens"]:,} | 招标文件上下文+大纲指令+片段 |')
    lines.append(f'| 输出 token | {summary["total_output_tokens"]:,} | 各章节正文生成 |')
    lines.append(f'| 去 AI 痕迹 token | {summary["total_deai_tokens"]:,} | 红旗词扫描+改写 |')
    lines.append(f'| 质量检查 token | {summary["qa_tokens"]:,} | 相关性+一致性检查 |')
    lines.append(f'| 合并 Word token | {summary["merge_tokens"]:,} | 合并+模板转换 |')
    lines.append(f'| **总计** | **{summary["total_tokens"]:,}** | |')
    lines.append('')

    lines.append('### 时间估算')
    lines.append('')
    lines.append('| 模式 | 预计耗时 | 说明 |')
    lines.append('|------|---------|------|')
    lines.append(f'| 并发编写（推荐） | **{summary["concurrent_time_str"]}** | {summary["concurrent_batches"]}章并发+QA+合并 |')
    lines.append(f'| 串行编写 | {summary["serial_time_str"]} | 逐章编写+QA+合并 |')
    lines.append('')

    # 各章节明细
    lines.append('## 各章节估算明细')
    lines.append('')
    lines.append('| 章节 | 分值 | H2数 | H3数 | 目标字数 | 输入token | 输出token | 编写时间 |')
    lines.append('|------|------|------|------|---------|----------|----------|---------|')
    for est in chapter_estimates:
        score_str = f'{est["score"]:.0f}' if est['score'] else '-'
        chars_str = f'{est["target_chars"]:,}' if est['target_chars'] else '-'
        lines.append(
            f'| {est["title"]} | {score_str} | {est["h2_count"]} | {est["h3_count"]} | '
            f'{chars_str} | {est["input_tokens"]:,} | {est["output_tokens"]:,} | '
            f'{_format_time(est["total_time_min"])} |'
        )
    lines.append('')

    # 优化建议
    lines.append('## 优化建议')
    lines.append('')
    # 找出最耗时的章节
    longest = max(chapter_estimates, key=lambda e: e['total_time_min'])
    lines.append(f'- 最耗时章节：**{longest["title"]}**（{_format_time(longest["total_time_min"])}），')
    lines.append(f'  建议优先使用片段库加速')
    lines.append(f'- 并发编写可节省约 {_format_time(summary["serial_time_min"] - summary["concurrent_time_min"])}')
    lines.append(f'- 总 token 约 {summary["total_tokens"]:,}，')
    lines.append(f'  如需控制用量，可减少低分值章节的字数分配')
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

def cmd_estimate(args):
    """估算 token 和时间"""
    outline_path = None
    target_pages = None
    eval_path = None
    output_path = None
    with_tables = False

    # 解析参数
    i = 0
    while i < len(args):
        if args[i] == '--pages':
            target_pages = int(args[i + 1])
            i += 2
        elif args[i] == '--eval':
            eval_path = args[i + 1]
            i += 2
        elif args[i] == '--output':
            output_path = args[i + 1]
            i += 2
        elif args[i] == '--with-tables':
            with_tables = True
            i += 1
        elif not outline_path:
            outline_path = args[i]
            i += 1
        else:
            i += 1

    if not outline_path or not target_pages:
        print('用法: python estimate_tokens.py estimate <大纲.md> --pages <目标页数> [--eval <eval_criteria.json>] [--with-tables] [--output <输出.md>]')
        return 1

    if not os.path.exists(outline_path):
        print(f'错误：大纲文件不存在: {outline_path}')
        return 1

    print(f'解析大纲: {outline_path}')
    chapters = parse_outline(outline_path)
    print(f'  共 {len(chapters)} 个一级章节')

    eval_data = None
    if eval_path and os.path.exists(eval_path):
        print(f'加载评分标准: {eval_path}')
        eval_data = load_eval_scores(eval_path)
        if eval_data:
            print(f'  总分: {eval_data["total_score"]}, 评分项: {len(eval_data["items"])}')

    print(f'\n目标: {target_pages} 页 ≈ {target_pages * CHARS_PER_PAGE:,} 字')
    if with_tables:
        print(f'模式: ✅ 添加表格图表（输出 token 系数 1.3→1.5, 输入 +5%）')
    else:
        print(f'模式: 纯文字（无表格图表）')
    print(f'估算中...')

    chapter_estimates, summary = estimate(chapters, target_pages, eval_data, with_tables=with_tables)

    # 控制台输出摘要
    print(f'\n{"=" * 60}')
    print(f'估算结果')
    print(f'{"=" * 60}')
    print(f'总 Token: {summary["total_tokens"]:,}')
    print(f'  - 输入: {summary["total_input_tokens"]:,}')
    print(f'  - 输出: {summary["total_output_tokens"]:,}')
    print(f'  - 去AI痕迹: {summary["total_deai_tokens"]:,}')
    print(f'  - QA+合并: {summary["qa_tokens"] + summary["merge_tokens"]:,}')
    print(f'预计耗时（并发）: {summary["concurrent_time_str"]}')
    print(f'预计耗时（串行）: {summary["serial_time_str"]}')

    # 生成报告
    report = generate_report(chapter_estimates, summary, output_path)

    if not output_path:
        print(f'\n{report}')

    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    if command == 'estimate':
        sys.exit(cmd_estimate(args))
    else:
        print(f'未知命令: {command}')
        print('可用命令: estimate')
        sys.exit(1)


if __name__ == '__main__':
    main()
