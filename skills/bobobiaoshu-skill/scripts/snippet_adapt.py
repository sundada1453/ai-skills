#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
片段适配检查器 v1.0
检测片段中残留的原项目专属字眼（公司名、系统名、项目名等），确保复用时不会泄露到新标书中。

功能:
  check   - 检查片段中的原项目字眼，报告需要替换的内容
  adapt   - 检查并自动替换（需提供替换映射）
  batch   - 批量检查某个目录下所有片段

用法:
  python snippet_adapt.py check <片段文件.md> [--project <当前项目名>] [--company <当前公司名>]
  python snippet_adapt.py adapt <片段文件.md> --mapping <替换映射JSON> [--output <输出文件>]
  python snippet_adapt.py batch <目录> [--project <当前项目名>]

示例:
  # 检查片段中的原项目字眼
  python snippet_adapt.py check snippets/安全规划/4GDPI维保_弱口令排查与加固方案.md

  # 检查并指定当前项目信息
  python snippet_adapt.py check snippets/运维保障/4GDPI维保_周巡检工作方案.md --project "漏洞管理平台运营服务" --company "中电福富"

  # 自动替换
  python snippet_adapt.py adapt snippet.md --mapping '{"4G统一DPI系统": "漏洞管理平台", "贵州泰若": "中电福富"}' --output adapted.md
"""

import sys
import os
import re
import json
from pathlib import Path

# ============================================================
# 已知项目专属词库（从历史标书中提取）
# ============================================================

# 所有历史项目中的公司名（投标方）
KNOWN_COMPANIES = [
    "贵州泰若数字科技有限公司",
    "成都巴蜀云基科技有限公司",
    "福州尚水数字科技有限公司",
    "上海航天电源技术有限责任公司",
    "北京合力思腾科技股份有限公司",
    "福建八闽云安信息技术有限公司",
    "宇动源（北京）信息技术有限公司",
    "宇动源(北京)信息技术有限公司",
    "天津赢达信科技有限公司",
    "北京领齐科技有限公司",
    "天迅瑞达",
    "中电福富",
    "中电福富信息科技有限公司",
]

# 所有历史项目中的系统名/产品名
KNOWN_SYSTEMS = [
    "4G统一DPI系统",
    "4GDPI系统",
    "DPI系统",
    "监管平台",
    "网络信息安全实训平台",
    "实训平台",
    "资产管理平台",
    "流动数据安全",
    "业务运营平台",
    "运行安全管理平台",
    "漏洞管理平台",
    "个人数据安全保护系统",
    "人力资源协同",
]

# 所有历史项目名（简短形式）
KNOWN_PROJECTS = [
    "4GDPI维保",
    "4GDPI维保服务",
    "监管平台数据对接",
    "网络信息安全实训平台研发",
    "资产管理平台系统扩容",
    "资产管理平台系统考核改造",
    "流动数据安全能力提升",
    "业务系统网络安全三期保障",
    "运行安全管理平台升级",
    "业务运营平台开发",
    "数据安全大模型",
    "个人数据安全保护",
    "漏洞管理平台运营",
    "天翼视联",
]

# 人员姓名（从标书中出现的）
KNOWN_PERSONS = [
    "李政权", "陈谦", "石开良", "朱正喜", "陈博", "余秋链",
    "杨骏宇", "张宇森",
    "陈成旭", "叶锦玲", "周智龙", "陈飞", "王远媛",
    "安石峰", "张晨", "王亮", "王德佳", "肖圣才", "熊文波", "王之豪", "杨浩业",
]

# 招标方名称
KNOWN_CLIENTS = [
    "中国电信贵州公司",
    "中电福富信息科技有限公司",
    "中电信数智科技有限公司",
    "天翼视联",
    "同方股份有限公司",
]


def build_term_registry():
    """构建专属词注册表，返回 [(词, 类型), ...]"""
    registry = []
    for name in KNOWN_COMPANIES:
        registry.append((name, "公司名"))
    for name in KNOWN_SYSTEMS:
        registry.append((name, "系统名"))
    for name in KNOWN_PROJECTS:
        registry.append((name, "项目名"))
    for name in KNOWN_PERSONS:
        registry.append((name, "人员姓名"))
    for name in KNOWN_CLIENTS:
        registry.append((name, "招标方"))
    # 按长度降序排列，优先匹配长词
    registry.sort(key=lambda x: len(x[0]), reverse=True)
    return registry


def parse_snippet_meta(filepath):
    """从片段文件的头部元数据中提取来源项目信息"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read(2000)  # 只读前2000字符找元数据

    meta = {}
    # 匹配 > 来源项目: xxx
    m = re.search(r'>\s*来源项目:\s*(.+)', content)
    if m:
        meta['source_project'] = m.group(1).strip()
    # 匹配 > 章节层级: xxx
    m = re.search(r'>\s*章节层级:\s*(.+)', content)
    if m:
        meta['level'] = m.group(1).strip()
    return meta


def scan_terms(content, registry, exclude_terms=None):
    """扫描内容中的专属词

    Args:
        content: 文本内容
        registry: 专属词注册表
        exclude_terms: 需要排除的词列表（当前项目的词，不算残留）

    Returns:
        [(词, 类型, 出现次数, 示例上下文), ...]
    """
    exclude_set = set(exclude_terms or [])
    found = {}

    for term, term_type in registry:
        if term in exclude_set:
            continue
        count = content.count(term)
        if count > 0:
            # 提取上下文示例
            idx = content.find(term)
            start = max(0, idx - 20)
            end = min(len(content), idx + len(term) + 20)
            context = content[start:end].replace('\n', ' ').strip()
            found[term] = (term_type, count, context)

    # 按出现次数降序排列
    results = [(term, info[0], info[1], info[2]) for term, info in found.items()]
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def check_snippet(filepath, current_project=None, current_company=None, current_system=None):
    """检查片段中的原项目字眼

    Args:
        filepath: 片段文件路径
        current_project: 当前项目名（排除项）
        current_company: 当前公司名（排除项）
        current_system: 当前系统名（排除项）

    Returns:
        (found_terms, source_project)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    meta = parse_snippet_meta(filepath)
    source_project = meta.get('source_project', '未知')

    registry = build_term_registry()

    # 当前项目的词不算残留
    exclude = []
    if current_project:
        exclude.append(current_project)
    if current_company:
        exclude.append(current_company)
    if current_system:
        exclude.append(current_system)

    found = scan_terms(content, registry, exclude)

    return found, source_project


def adapt_snippet(filepath, mapping, output_path=None):
    """根据映射替换片段中的原项目字眼

    Args:
        filepath: 片段文件路径
        mapping: {原词: 新词} 字典
        output_path: 输出路径（默认覆盖原文件）

    Returns:
        (替换次数, 替换详情)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    total_replacements = 0
    details = []

    # 按原词长度降序排列，优先替换长词
    sorted_mapping = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)

    for old_term, new_term in sorted_mapping:
        count = content.count(old_term)
        if count > 0:
            content = content.replace(old_term, new_term)
            total_replacements += count
            details.append((old_term, new_term, count))

    if output_path is None:
        output_path = filepath

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return total_replacements, details


def batch_check(directory, current_project=None, current_company=None, current_system=None):
    """批量检查目录下所有片段"""
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f'错误: 目录不存在: {directory}')
        return

    md_files = list(dir_path.rglob('*.md'))
    if not md_files:
        print(f'目录中没有 .md 文件: {directory}')
        return

    total_files = 0
    total_issues = 0
    all_results = {}

    for md_file in md_files:
        found, source = check_snippet(str(md_file), current_project, current_company, current_system)
        if found:
            total_files += 1
            total_issues += len(found)
            all_results[str(md_file)] = {
                'source_project': source,
                'terms': [(t, ty, c, ctx) for t, ty, c, ctx in found]
            }

    # 输出汇总
    print(f'扫描 {len(md_files)} 个文件，{total_files} 个有残留字眼，共 {total_issues} 个专属词\n')

    # 按词频汇总
    term_freq = {}
    for fpath, info in all_results.items():
        for term, term_type, count, ctx in info['terms']:
            if term not in term_freq:
                term_freq[term] = {'type': term_type, 'total': 0, 'files': 0}
            term_freq[term]['total'] += count
            term_freq[term]['files'] += 1

    print('=== 专属词频率排行 ===')
    for term, info in sorted(term_freq.items(), key=lambda x: x[1]['total'], reverse=True):
        print(f'  [{info["type"]}] "{term}" — 共 {info["total"]} 次，出现在 {info["files"]} 个文件')

    return all_results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'check':
        if len(sys.argv) < 3:
            print('用法: snippet_adapt.py check <片段文件.md> [--project <当前项目名>] [--company <当前公司名>] [--system <当前系统名>]')
            sys.exit(1)

        filepath = sys.argv[2]
        current_project = None
        current_company = None
        current_system = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--project' and i + 1 < len(args):
                current_project = args[i + 1]; i += 2
            elif args[i] == '--company' and i + 1 < len(args):
                current_company = args[i + 1]; i += 2
            elif args[i] == '--system' and i + 1 < len(args):
                current_system = args[i + 1]; i += 2
            else:
                i += 1

        found, source = check_snippet(filepath, current_project, current_company, current_system)

        print(f'片段文件: {filepath}')
        print(f'来源项目: {source}')
        print(f'当前项目: {current_project or "未指定"}')
        print(f'当前公司: {current_company or "未指定"}')
        print(f'当前系统: {current_system or "未指定"}')
        print()

        if found:
            print(f'⚠ 发现 {len(found)} 个原项目专属字眼:\n')
            print(f'{"类型":<8} {"专属词":<30} {"次数":<6} {"示例上下文"}')
            print('-' * 100)
            for term, term_type, count, ctx in found:
                print(f'{term_type:<8} {term:<30} {count:<6} ...{ctx}...')
            print()
            print('⚠ 以上字眼在改写时必须替换为当前项目的对应信息。')
            print('  使用 adapt 命令可自动替换:')
            print(f'  python snippet_adapt.py adapt "{filepath}" --mapping \'{{"原词": "新词"}}\' --output 输出.md')
        else:
            print('✓ 未发现原项目专属字眼，片段可直接复用。')

    elif cmd == 'adapt':
        if len(sys.argv) < 4:
            print('用法: snippet_adapt.py adapt <片段文件.md> --mapping <JSON> [--output <输出文件>]')
            sys.exit(1)

        filepath = sys.argv[2]
        mapping_str = None
        output = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--mapping' and i + 1 < len(args):
                mapping_str = args[i + 1]; i += 2
            elif args[i] == '--output' and i + 1 < len(args):
                output = args[i + 1]; i += 2
            else:
                i += 1

        if not mapping_str:
            print('错误: 必须指定 --mapping')
            sys.exit(1)

        try:
            mapping = json.loads(mapping_str)
        except json.JSONDecodeError as e:
            print(f'错误: mapping JSON 解析失败: {e}')
            sys.exit(1)

        total, details = adapt_snippet(filepath, mapping, output)

        print(f'替换完成: {total} 处替换')
        for old, new, count in details:
            print(f'  "{old}" → "{new}" ({count} 次)')
        if output:
            print(f'输出文件: {output}')
        else:
            print(f'已覆盖原文件: {filepath}')

    elif cmd == 'batch':
        if len(sys.argv) < 3:
            print('用法: snippet_adapt.py batch <目录> [--project <当前项目名>] [--company <当前公司名>] [--system <当前系统名>]')
            sys.exit(1)

        directory = sys.argv[2]
        current_project = None
        current_company = None
        current_system = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--project' and i + 1 < len(args):
                current_project = args[i + 1]; i += 2
            elif args[i] == '--company' and i + 1 < len(args):
                current_company = args[i + 1]; i += 2
            elif args[i] == '--system' and i + 1 < len(args):
                current_system = args[i + 1]; i += 2
            else:
                i += 1

        batch_check(directory, current_project, current_company, current_system)

    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
