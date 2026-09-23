#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案片段管理器 v1.0
管理标书通用片段的抽取、存储、检索和复用。

功能:
  save    - 从已完成的 Markdown 文档中抽取通用片段，存入 memory/snippets/
  list    - 列出所有已存储的片段
  search  - 按关键词搜索片段
  load    - 加载指定片段，输出到 stdout 或文件
  merge   - 将多个片段合并为一个草稿

用法:
  python snippet_manager.py save <源文件.md> --category <类别> [--name <片段名>]
  python snippet_manager.py list [--category <类别>]
  python snippet_manager.py search <关键词>
  python snippet_manager.py load <类别/片段名> [--output <输出文件>]
  python snippet_manager.py merge <类别/片段1> <类别/片段2> ... --output <输出文件>

示例:
  # 从已完成的风险评估方案抽取片段
  python snippet_manager.py save 风险评估方案.md --category 风险评估

  # 列出所有风险评估类片段
  python snippet_manager.py list --category 风险评估

  # 搜索含"预警"的片段
  python snippet_manager.py search 预警

  # 加载片段用于新项目
  python snippet_manager.py load 风险评估/风险监控 --output 新项目_风险监控.md
"""

import sys
import os
import re
import json
import shutil
from datetime import datetime

# memory 根目录（默认）
DEFAULT_MEMORY_ROOT = os.path.join(os.path.expanduser('~'), 'Desktop', '2026招投标', 'memory')


def get_memory_root():
    """获取 memory 根目录"""
    root = os.environ.get('BIAOSHU_MEMORY_ROOT', DEFAULT_MEMORY_ROOT)
    return root


def get_snippets_dir():
    """获取片段存储目录"""
    return os.path.join(get_memory_root(), 'snippets')


def get_outlines_dir():
    """获取大纲模板目录"""
    return os.path.join(get_memory_root(), 'outlines')


# ============================================================
# 片段抽取
# ============================================================

def extract_sections(md_content):
    """从 Markdown 内容中按 ### 级别切分章节片段

    每个 ### 小节作为一个独立片段，保留其上层 ## 标题作为分类上下文。
    返回: [(片段名, 父章节, 内容), ...]
    """
    sections = []
    current_h2 = ''
    current_h3 = ''
    current_content_lines = []

    def _save_section():
        if current_h3 and current_content_lines:
            content = '\n'.join(current_content_lines).strip()
            if len(content) > 50:  # 过短的不存
                sections.append((current_h3, current_h2, content))

    for line in md_content.split('\n'):
        if line.startswith('## '):
            _save_section()
            current_h2 = line[3:].strip()
            current_h3 = ''
            current_content_lines = []
        elif line.startswith('### '):
            _save_section()
            current_h3 = line[4:].strip()
            current_content_lines = []
        elif current_h3:
            current_content_lines.append(line)

    _save_section()
    return sections


def extract_h2_sections(md_content):
    """按 ## 级别切分大章节片段（含其下所有 ### 子节）

    返回: [(章节名, 内容), ...]
    """
    sections = []
    current_h2 = ''
    current_content_lines = []

    def _save_section():
        if current_h2 and current_content_lines:
            content = '\n'.join(current_content_lines).strip()
            if len(content) > 100:
                sections.append((current_h2, content))

    for line in md_content.split('\n'):
        if line.startswith('## '):
            _save_section()
            current_h2 = line[3:].strip()
            current_content_lines = []
        elif current_h2:
            # 跳过 # 一级标题
            if not line.startswith('# '):
                current_content_lines.append(line)

    _save_section()
    return sections


def save_snippets(source_path, category, name=None):
    """从源文件抽取片段并保存

    Args:
        source_path: 源 Markdown 文件路径
        category: 片段类别（对应 snippets/ 下的子目录）
        name: 可选的自定义片段名（默认使用源文件名）
    """
    if not os.path.exists(source_path):
        print(f'错误: 文件不存在: {source_path}')
        return False

    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()

    snippets_dir = os.path.join(get_snippets_dir(), category)
    os.makedirs(snippets_dir, exist_ok=True)

    base_name = name or os.path.splitext(os.path.basename(source_path))[0]

    # 按 ## 大章节抽取
    h2_sections = extract_h2_sections(content)
    # 按 ### 小节抽取
    h3_sections = extract_sections(content)

    # 保存整体文件（完整版本）
    full_path = os.path.join(snippets_dir, f'{base_name}_完整.md')
    shutil.copy2(source_path, full_path)
    print(f'完整方案: {full_path}')

    # 保存 ## 级片段
    h2_dir = os.path.join(snippets_dir, 'chapters')
    os.makedirs(h2_dir, exist_ok=True)
    for sec_name, sec_content in h2_sections:
        # 清理文件名
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', sec_name)
        sec_path = os.path.join(h2_dir, f'{safe_name}.md')
        with open(sec_path, 'w', encoding='utf-8') as f:
            f.write(f'# {sec_name}\n\n')
            f.write(sec_content)
        print(f'  章节: {safe_name}.md ({len(sec_content)} 字符)')

    # 保存 ### 级片段
    h3_dir = os.path.join(snippets_dir, 'sections')
    os.makedirs(h3_dir, exist_ok=True)
    for sec_name, parent_h2, sec_content in h3_sections:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', sec_name)
        sec_path = os.path.join(h3_dir, f'{safe_name}.md')
        # 在文件头添加元数据
        with open(sec_path, 'w', encoding='utf-8') as f:
            f.write(f'<!--\n')
            f.write(f'parent: {parent_h2}\n')
            f.write(f'source: {base_name}\n')
            f.write(f'saved: {datetime.now().strftime("%Y-%m-%d")}\n')
            f.write(f'-->\n\n')
            f.write(f'### {sec_name}\n\n')
            f.write(sec_content)
        print(f'  小节: {safe_name}.md ({len(sec_content)} 字符, 父章节: {parent_h2})')

    # 保存索引
    index_path = os.path.join(snippets_dir, 'index.json')
    index = {}
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)

    index[base_name] = {
        'source': os.path.basename(source_path),
        'category': category,
        'saved': datetime.now().strftime('%Y-%m-%d'),
        'h2_count': len(h2_sections),
        'h3_count': len(h3_sections),
        'total_chars': len(content),
    }

    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f'\n索引已更新: {index_path}')
    print(f'共保存 {len(h2_sections)} 个章节 + {len(h3_sections)} 个小节')
    return True


# ============================================================
# 片段列表
# ============================================================

def list_snippets(category=None):
    """列出已存储的片段"""
    snippets_dir = get_snippets_dir()
    if not os.path.exists(snippets_dir):
        print('暂无片段，请先使用 save 命令存入片段')
        return

    if category:
        dirs = [os.path.join(snippets_dir, category)]
    else:
        dirs = [os.path.join(snippets_dir, d) for d in os.listdir(snippets_dir)
                if os.path.isdir(os.path.join(snippets_dir, d))]

    for d in dirs:
        if not os.path.isdir(d):
            continue
        cat_name = os.path.basename(d)
        print(f'\n=== {cat_name} ===')

        # 读取索引
        index_path = os.path.join(d, 'index.json')
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
            for name, info in index.items():
                print(f'  {name}: {info["h2_count"]} 章节 + {info["h3_count"]} 小节'
                      f' ({info["total_chars"]} 字符, 存于 {info["saved"]})')

        # 列出章节文件
        chapters_dir = os.path.join(d, 'chapters')
        if os.path.exists(chapters_dir):
            files = [f for f in os.listdir(chapters_dir) if f.endswith('.md')]
            if files:
                print(f'  章节片段 ({len(files)}):')
                for f in sorted(files):
                    print(f'    - chapters/{f}')

        # 列出小节文件
        sections_dir = os.path.join(d, 'sections')
        if os.path.exists(sections_dir):
            files = [f for f in os.listdir(sections_dir) if f.endswith('.md')]
            if files:
                print(f'  小节片段 ({len(files)}):')
                for f in sorted(files):
                    print(f'    - sections/{f}')


# ============================================================
# 片段搜索
# ============================================================

def search_snippets(keyword):
    """按关键词搜索片段"""
    snippets_dir = get_snippets_dir()
    if not os.path.exists(snippets_dir):
        print('暂无片段')
        return

    results = []
    for root, dirs, files in os.walk(snippets_dir):
        for fname in files:
            if not fname.endswith('.md'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            if keyword.lower() in content.lower():
                # 找到匹配，提取上下文
                lines = content.split('\n')
                contexts = []
                for i, line in enumerate(lines):
                    if keyword.lower() in line.lower():
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        ctx = ' ... '.join(lines[start:end]).strip()
                        contexts.append(ctx)
                        if len(contexts) >= 3:
                            break

                rel_path = os.path.relpath(fpath, snippets_dir)
                results.append((rel_path, contexts))

    if results:
        print(f'搜索 "{keyword}" 找到 {len(results)} 个片段:\n')
        for path, contexts in results:
            print(f'  {path}')
            for ctx in contexts:
                print(f'    → {ctx[:80]}')
            print()
    else:
        print(f'搜索 "{keyword}" 未找到匹配片段')


# ============================================================
# 片段加载
# ============================================================

def load_snippet(ref, output_path=None):
    """加载指定片段

    Args:
        ref: 片段引用，格式: 类别/片段名 或 类别/chapters/片段名 或 类别/sections/片段名
        output_path: 输出文件路径（可选，默认输出到 stdout）
    """
    snippets_dir = get_snippets_dir()

    # 尝试多种路径组合
    candidates = [
        os.path.join(snippets_dir, ref),
        os.path.join(snippets_dir, ref + '.md'),
        os.path.join(snippets_dir, ref, '完整.md'),
    ]

    # 如果 ref 是 "类别/名称"，尝试找完整版本
    parts = ref.replace('\\', '/').split('/')
    if len(parts) == 2:
        cat, name = parts
        candidates.extend([
            os.path.join(snippets_dir, cat, f'{name}_完整.md'),
            os.path.join(snippets_dir, cat, 'chapters', f'{name}.md'),
            os.path.join(snippets_dir, cat, 'sections', f'{name}.md'),
        ])

    found_path = None
    for c in candidates:
        if os.path.exists(c):
            found_path = c
            break

    if not found_path:
        print(f'错误: 未找到片段 "{ref}"')
        print(f'尝试路径: {candidates}')
        return False

    with open(found_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'片段已保存: {output_path} ({len(content)} 字符)')
    else:
        print(content)

    return True


# ============================================================
# 片段合并
# ============================================================

def merge_snippets(refs, output_path):
    """合并多个片段为一个草稿

    Args:
        refs: 片段引用列表
        output_path: 输出文件路径
    """
    merged = []

    for ref in refs:
        snippets_dir = get_snippets_dir()
        # 查找片段
        candidates = [
            os.path.join(snippets_dir, ref),
            os.path.join(snippets_dir, ref + '.md'),
        ]
        parts = ref.replace('\\', '/').split('/')
        if len(parts) == 2:
            cat, name = parts
            candidates.extend([
                os.path.join(snippets_dir, cat, 'chapters', f'{name}.md'),
                os.path.join(snippets_dir, cat, 'sections', f'{name}.md'),
            ])

        found = None
        for c in candidates:
            if os.path.exists(c):
                found = c
                break

        if found:
            with open(found, 'r', encoding='utf-8') as f:
                content = f.read()
            # 去掉元数据注释
            content = re.sub(r'<!--[\s\S]*?-->\s*', '', content).strip()
            merged.append(content)
            print(f'  + {ref} ({len(content)} 字符)')
        else:
            print(f'  ✗ {ref} 未找到，跳过')

    if merged:
        full_content = '\n\n---\n\n'.join(merged)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_content)
        print(f'\n合并完成: {output_path} ({len(full_content)} 字符)')
        return True
    else:
        print('无有效片段，合并失败')
        return False


# ============================================================
# 主函数
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'save':
        if len(sys.argv) < 4:
            print('用法: snippet_manager.py save <源文件.md> --category <类别> [--name <名称>]')
            sys.exit(1)
        source = sys.argv[2]
        category = None
        name = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--category' and i + 1 < len(args):
                category = args[i + 1]; i += 2
            elif args[i] == '--name' and i + 1 < len(args):
                name = args[i + 1]; i += 2
            else:
                i += 1
        if not category:
            print('错误: 必须指定 --category')
            sys.exit(1)
        save_snippets(source, category, name)

    elif cmd == 'list':
        category = None
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == '--category' and i + 1 < len(args):
                category = args[i + 1]; i += 2
            else:
                i += 1
        list_snippets(category)

    elif cmd == 'search':
        if len(sys.argv) < 3:
            print('用法: snippet_manager.py search <关键词>')
            sys.exit(1)
        search_snippets(sys.argv[2])

    elif cmd == 'load':
        if len(sys.argv) < 3:
            print('用法: snippet_manager.py load <类别/片段名> [--output <文件>]')
            sys.exit(1)
        ref = sys.argv[2]
        output = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--output' and i + 1 < len(args):
                output = args[i + 1]; i += 2
            else:
                i += 1
        load_snippet(ref, output)

    elif cmd == 'merge':
        if len(sys.argv) < 4:
            print('用法: snippet_manager.py merge <片段1> <片段2> ... --output <文件>')
            sys.exit(1)
        refs = []
        output = None
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == '--output' and i + 1 < len(args):
                output = args[i + 1]; i += 2
            else:
                refs.append(args[i]); i += 1
        if not output:
            print('错误: 必须指定 --output')
            sys.exit(1)
        merge_snippets(refs, output)

    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
