#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小波标书助手V9.0 - 配置管理器 v1.0

首次使用时初始化配置，后续自动加载。
配置保存在 skill 目录下 config.json，包含：
  - memory_name: memory 目录名称（用于构建片段库/术语库路径）
  - memory_path: memory 目录完整路径（自动生成）
  - template_path: 标书 Word 模板路径
  - history_bid_path: 历史标书目录路径（可选，用于自动分析）
  - output_dir: 标书终稿默认输出目录
  - industry: 行业类型（telecom/it/construction/transport/finance/other）

用法:
    # 检查是否已配置
    python config_manager.py check

    # 初始化配置
    python config_manager.py init --memory-name "2026招投标" --template "C:/path/to/template.docx" --output "C:/path/to/output" --industry telecom [--history "C:/path/to/history"]

    # 加载配置（JSON 格式输出）
    python config_manager.py load

    # 获取单个配置项
    python config_manager.py get template_path

    # 更新单个配置项
    python config_manager.py update --key template_path --value "C:/new/template.docx"

    # 重置配置（删除 config.json，下次使用时重新引导）
    python config_manager.py reset
"""

import os
import sys
import json
import argparse
from datetime import datetime

# Config 文件位置：skill 根目录下
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SKILL_DIR, 'config.json')

# 行业类型映射
INDUSTRIES = {
    'telecom': '电信',
    'it': 'IT/信息化',
    'construction': '建筑/工程',
    'transport': '交通',
    'finance': '金融',
    'other': '其他',
}

# 行业默认片段库分类
INDUSTRY_SNIPPET_CATEGORIES = {
    'telecom': ['网络安全', '系统运维', '通信工程', '云计算', '数据安全', '项目管理', '风险评估'],
    'it': ['软件开发', '系统集成', '信息安全', '数据库', '项目管理', '风险评估', '运维服务'],
    'construction': ['工程施工', '安全管理', '质量控制', '进度管理', '造价预算', '验收方案'],
    'transport': ['交通工程', '航道工程', '安全管理', '质量控制', '进度管理', '验收方案'],
    'finance': ['金融科技', '数据安全', '系统运维', '合规管理', '风险评估', '项目管理'],
    'other': ['项目管理', '风险评估', '质量管理', '售后服务', '培训方案', '验收方案'],
}

# 行业默认术语种子
INDUSTRY_VOCAB_SEEDS = {
    'telecom': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('天翼云', '天翼云/中国电信云', '统一使用天翼云'),
        ('等保2.0', '等保二级 / 等保三级', '具体级别明确标注'),
    ],
    'it': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('SLA', 'sla / Sla', '全大写'),
        ('API', 'api / Api', '全大写'),
    ],
    'construction': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('项目经理', '项目负责人 / 项目总监', '统一用项目经理'),
    ],
    'transport': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('交工验收', '竣工验收', '交工验收指施工完成后初步验收'),
    ],
    'finance': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('等保2.0', '等保二级 / 等保三级', '具体级别明确标注'),
    ],
    'other': [
        ('7×24小时', '7*24 / 7x24', '乘号用×'),
        ('项目负责人', '项目经理 / 项目总监', '全文统一一种'),
    ],
}


def get_desktop():
    """获取桌面路径"""
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def build_memory_path(memory_name):
    """根据 memory 名称构建 memory 目录路径

    路径格式: {桌面}/{memory_name}/memory/
    """
    desktop = get_desktop()
    return os.path.join(desktop, memory_name, 'memory')


def create_memory_structure(memory_path, industry='other'):
    """创建 memory 目录结构

    根据行业类型创建对应的片段库分类目录和术语库种子文件。
    """
    # 基础目录
    dirs = [
        memory_path,
        os.path.join(memory_path, 'snippets'),
        os.path.join(memory_path, 'vocabulary'),
        os.path.join(memory_path, 'outlines'),
        os.path.join(memory_path, 'projects'),
    ]

    # 行业默认片段分类
    categories = INDUSTRY_SNIPPET_CATEGORIES.get(industry, INDUSTRY_SNIPPET_CATEGORIES['other'])
    for cat in categories:
        dirs.append(os.path.join(memory_path, 'snippets', cat))

    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # 创建默认术语表
    vocab_path = os.path.join(memory_path, 'vocabulary', '术语表.md')
    if not os.path.exists(vocab_path):
        seeds = INDUSTRY_VOCAB_SEEDS.get(industry, INDUSTRY_VOCAB_SEEDS['other'])
        with open(vocab_path, 'w', encoding='utf-8') as f:
            f.write('# 术语表\n\n')
            f.write('| 统一写法 | 禁止写法 | 说明 |\n')
            f.write('|---------|---------|------|\n')
            for unified, forbidden, note in seeds:
                f.write(f'| {unified} | {forbidden} | {note} |\n')
            f.write('\n')

    print(f'memory 目录已创建: {memory_path}')
    print(f'  片段分类: {", ".join(categories)}')
    print(f'  术语种子: {len(INDUSTRY_VOCAB_SEEDS.get(industry, []))} 条')
    return dirs


def check_config():
    """检查配置是否存在

    输出格式:
        CONFIG_EXISTS + JSON 配置
        或
        CONFIG_NOT_FOUND
    """
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if config.get('initialized'):
                print('CONFIG_EXISTS')
                print(json.dumps(config, ensure_ascii=False, indent=2))
                return True
        except Exception as e:
            print(f'CONFIG_ERROR: {e}')
            return False
    print('CONFIG_NOT_FOUND')
    return False


def init_config(memory_name, template_path, output_dir, industry, history_bid_path=None):
    """初始化配置

    Args:
        memory_name: memory 目录名称
        template_path: 标书模板 .docx 文件路径
        output_dir: 默认输出目录
        industry: 行业类型 (telecom/it/construction/transport/finance/other)
        history_bid_path: 历史标书目录路径（可选）
    """
    # 验证模板路径
    if template_path:
        if not os.path.exists(template_path):
            print(f'WARNING: 模板文件不存在: {template_path}')
        elif not template_path.lower().endswith('.docx'):
            print(f'WARNING: 模板文件不是 .docx 格式: {template_path}')

    # 构建 memory 路径
    memory_path = build_memory_path(memory_name)

    # 创建 memory 目录结构
    create_memory_structure(memory_path, industry)

    # 验证历史标书路径
    if history_bid_path:
        if not os.path.exists(history_bid_path):
            print(f'WARNING: 历史标书路径不存在: {history_bid_path}')
            history_bid_path = None
        else:
            # 统计历史标书文件
            docx_files = [f for f in os.listdir(history_bid_path)
                          if f.lower().endswith(('.docx', '.doc', '.pdf'))]
            print(f'历史标书目录: {history_bid_path}')
            print(f'  发现 {len(docx_files)} 个文档文件: {", ".join(docx_files[:5])}{"..." if len(docx_files) > 5 else ""}')

    # 创建输出目录
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    config = {
        'version': '1.0',
        'initialized': True,
        'init_date': datetime.now().strftime('%Y-%m-%d'),
        'memory_name': memory_name,
        'memory_path': memory_path,
        'template_path': template_path,
        'history_bid_path': history_bid_path,
        'output_dir': output_dir,
        'industry': industry,
        'industry_name': INDUSTRIES.get(industry, industry),
    }

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f'\n配置已保存: {CONFIG_PATH}')
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return config


def load_config():
    """加载配置并输出 JSON"""
    if not os.path.exists(CONFIG_PATH):
        print('ERROR: 配置文件不存在，请先执行 init')
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return config


def get_value(key):
    """获取单个配置项"""
    if not os.path.exists(CONFIG_PATH):
        print('ERROR: 配置文件不存在')
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    if key in config:
        print(config[key])
    else:
        print(f'ERROR: 配置项不存在: {key}')
        sys.exit(1)


def update_value(key, value):
    """更新单个配置项"""
    if not os.path.exists(CONFIG_PATH):
        print('ERROR: 配置文件不存在')
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 特殊处理：更新 memory_name 时同步更新 memory_path
    if key == 'memory_name':
        config['memory_name'] = value
        config['memory_path'] = build_memory_path(value)
        # 如果新 memory 目录不存在，创建它
        if not os.path.exists(config['memory_path']):
            create_memory_structure(config['memory_path'], config.get('industry', 'other'))
    else:
        config[key] = value

    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f'已更新: {key} = {config.get(key)}')


def reset_config():
    """重置配置（删除 config.json）"""
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
        print(f'配置已删除: {CONFIG_PATH}')
        print('下次使用时将重新执行首次配置引导。')
    else:
        print('配置文件不存在，无需重置。')


def scan_history_bids(history_path, memory_path):
    """扫描历史标书目录，输出文件列表供 agent 分析

    不直接提取片段，而是输出结构化信息，由 agent 使用
    parse_bid_files.py 和 snippet_manager.py 完成提取。
    """
    if not os.path.exists(history_path):
        print(f'ERROR: 路径不存在: {history_path}')
        return

    files = []
    for f in os.listdir(history_path):
        if f.lower().endswith(('.docx', '.doc', '.pdf', '.md')):
            filepath = os.path.join(history_path, f)
            size_kb = round(os.path.getsize(filepath) / 1024, 1)
            files.append({
                'filename': f,
                'path': filepath,
                'size_kb': size_kb,
                'type': f.split('.')[-1].lower(),
            })

    print(f'历史标书目录: {history_path}')
    print(f'文档总数: {len(files)}')
    print()
    for i, f in enumerate(files, 1):
        print(f'{i}. {f["filename"]} ({f["size_kb"]} KB, {f["type"]})')
        print(f'   路径: {f["path"]}')

    if files:
        print(f'\n建议分析流程:')
        print(f'1. 对每个文档运行 parse_bid_files.py 提取文本')
        print(f'2. 对提取的内容运行 snippet_manager.py save 存入片段库')
        print(f'3. 从文档中提取行业术语，追加到 {memory_path}/vocabulary/术语表.md')
        print(f'4. 片段库路径: {memory_path}/snippets/')

    return files


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='小波标书助手V9.0 - 配置管理器 v1.0')
    subparsers = parser.add_subparsers(dest='command')

    # check
    sub_check = subparsers.add_parser('check', help='检查配置是否存在')

    # init
    sub_init = subparsers.add_parser('init', help='初始化配置')
    sub_init.add_argument('--memory-name', required=True, help='memory 目录名称（如 "2026招投标"）')
    sub_init.add_argument('--template', required=True, help='标书模板 .docx 文件路径')
    sub_init.add_argument('--output', required=True, help='默认输出目录')
    sub_init.add_argument('--industry', required=True, choices=list(INDUSTRIES.keys()),
                          help='行业类型: telecom/it/construction/transport/finance/other')
    sub_init.add_argument('--history', help='历史标书目录路径（可选，用于自动分析提取片段和术语）')

    # load
    sub_load = subparsers.add_parser('load', help='加载配置（JSON 格式输出）')

    # get
    sub_get = subparsers.add_parser('get', help='获取单个配置项')
    sub_get.add_argument('key', help='配置项名称（如 template_path、memory_path、output_dir 等）')

    # update
    sub_update = subparsers.add_parser('update', help='更新单个配置项')
    sub_update.add_argument('--key', required=True, help='配置项名称')
    sub_update.add_argument('--value', required=True, help='配置项值')

    # reset
    sub_reset = subparsers.add_parser('reset', help='重置配置（删除 config.json）')

    # scan-history
    sub_scan = subparsers.add_parser('scan-history', help='扫描历史标书目录，输出文件列表')
    sub_scan.add_argument('--path', help='历史标书路径（默认从 config.json 读取）')
    sub_scan.add_argument('--memory-path', help='memory 目录路径（默认从 config.json 读取）')

    args = parser.parse_args()

    if args.command == 'check':
        check_config()
    elif args.command == 'init':
        init_config(args.memory_name, args.template, args.output, args.industry, args.history)
    elif args.command == 'load':
        load_config()
    elif args.command == 'get':
        get_value(args.key)
    elif args.command == 'update':
        update_value(args.key, args.value)
    elif args.command == 'reset':
        reset_config()
    elif args.command == 'scan-history':
        # 从参数或 config.json 读取路径
        hist_path = args.path
        mem_path = args.memory_path
        if not hist_path or not mem_path:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                hist_path = hist_path or config.get('history_bid_path')
                mem_path = mem_path or config.get('memory_path')
        if not hist_path:
            print('ERROR: 未指定历史标书路径，且 config.json 中未配置')
            sys.exit(1)
        if not mem_path:
            print('ERROR: 未指定 memory 路径，且 config.json 中未配置')
            sys.exit(1)
        scan_history_bids(hist_path, mem_path)
    else:
        parser.print_help()
