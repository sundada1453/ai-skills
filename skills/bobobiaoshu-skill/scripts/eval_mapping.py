#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
评分点自动映射脚本 v1.0
从招标文件解析结果中提取评分标准，结构化为 JSON，并映射到标书章节。

功能:
  parse  - 从招标文件解析结果中提取评分标准，输出 eval_criteria.json
  map    - 将评分项映射到标书章节大纲，输出评分点映射表.md
  check  - 检查每个评分项是否都有对应章节覆盖
  report - 一键执行 parse + map + check，输出完整报告

用法:
  python eval_mapping.py parse <招标文件解析结果.md> [--output <输出目录>]
  python eval_mapping.py parse <招标文件解析结果.md> --scoring <评分标准文件.md/json>
  python eval_mapping.py map <eval_criteria.json> --outline <大纲.md> [--output <输出目录>]
  python eval_mapping.py check <eval_criteria.json> --outline <大纲.md>
  python eval_mapping.py report <招标文件解析结果.md> --outline <大纲.md> [--output <输出目录>]

示例:
  # 从招标文件解析结果中提取评分标准
  python eval_mapping.py parse 招标文件_解析结果.md --output 项目目录/

  # 使用单独的评分标准文件（当PDF表格未提取出来时）
  python eval_mapping.py parse 招标文件_解析结果.md --scoring 评分标准.md --output 项目目录/

  # 将评分项映射到章节大纲
  python eval_mapping.py map eval_criteria.json --outline 大纲.md --output 项目目录/

  # 一键生成完整报告
  python eval_mapping.py report 招标文件_解析结果.md --outline 大纲.md --output 项目目录/
"""

import sys
import os
import re
import json
from datetime import datetime

# 跨平台兼容
try:
    from macos_compat import get_python_cmd
except ImportError:
    def get_python_cmd():
        return 'python'


# ============================================================
# 评分标准提取
# ============================================================

# 评分类别关键词映射
CATEGORY_KEYWORDS = {
    '商务': ['商务', '资质', '业绩', '财务', '信誉', '营业执照', '认证证书', '管理体系'],
    '技术': ['技术', '方案', '实施', '人员', '团队', '项目管理', '质量', '进度', '售后',
             '运维', '安全', '培训', '应急', '理解', '分析', '设计', '开发', '测试',
             '验收', '驻场', '服务', '保障', '措施', '规划', '架构', '响应'],
    '价格': ['价格', '报价', '投标报价', '响应报价', '分项报价', '总价'],
}

# 评分因素到典型章节标题的关键词映射（用于自动映射）
FACTOR_TO_CHAPTER_KEYWORDS = {
    '项目理解': ['项目理解', '项目概况', '需求理解', '项目背景', '需求分析'],
    '技术方案': ['技术方案', '实施方案', '建设方案', '解决方案', '技术路线', '架构设计'],
    '人员配置': ['人员', '团队', '组织', '驻场', '人员信息', '服务团队'],
    '业绩': ['业绩', '同类项目', '项目经验', '合同'],
    '项目管理': ['项目管理', '进度', '质量', '风险管理', '计划'],
    '质量管理': ['质量', '质量管理', '质量控制', '质量保证'],
    '进度计划': ['进度', '计划', '时间', '里程碑', '工期'],
    '售后服务': ['售后', '维护', '运维', '服务保障', '服务方案'],
    '培训方案': ['培训', '知识转移', '赋能'],
    '应急预案': ['应急', '突发事件', '故障处理', '安全保障'],
    '安全方案': ['安全', '网络安全', '信息安全', '安全管理'],
    '企业实力': ['企业', '公司', '资质', '认证', '管理体系', '整体实力'],
    '开发过程': ['开发', '研发', '编码', '测试', '交付'],
    '报价': ['报价', '价格', '分项报价'],
    '服务方案': ['服务', '服务方案', '服务保障', '服务措施'],
    '设备保障': ['设备', '备件', '硬件', '巡检'],
}

# 客观评审项关键词（通过/不通过型）
OBJECTIVE_KEYWORDS = ['资格', '资质', '营业执照', '证书', '营业执照', '许可证',
                      '响应担保', '盖章', '签字', '格式', '密封', '有效期',
                      '营业执照', '社保', '纳税', '劳动合同']


def extract_scoring_from_text(text):
    """从招标文件解析文本中自动提取评分标准信息

    提取策略:
    1. 搜索总分组架（总分X分，商务X分，技术X分，价格X分）
    2. 搜索表格行（管道符分隔的表格）
    3. 搜索编号评分项（如"（1）项目理解 ... 5分"）
    4. 搜索评审办法前附表区域

    Returns:
        dict: {
            'total_score': int,
            'categories': [{'name': '商务', 'score': 10}, ...],
            'items': [{'id': 1, 'category': '技术', 'factor': '项目理解', 'score': 5, ...}],
            'raw_extraction': bool,  # 是否成功提取到详细评分项
            'notes': str  # 说明信息
        }
    """
    result = {
        'total_score': None,
        'categories': [],
        'items': [],
        'raw_extraction': False,
        'notes': ''
    }

    # --- 策略1: 提取总分组架 ---
    # 匹配: "总分共100分，其中商务10分，技术50分,价格40分"
    total_pattern = re.compile(
        r'总分[共]?(\d+)\s*分'
        r'[,，。；]?\s*其中'
        r'(.+?)(?=评审|详细|按照|$)',
        re.DOTALL
    )
    total_match = total_pattern.search(text)
    if total_match:
        result['total_score'] = int(total_match.group(1))
        # 提取各类别分值
        cat_text = total_match.group(2)
        # 匹配: 商务10分, 技术50分, 价格40分
        cat_pattern = re.compile(
            r'(商务|技术|价格|服务|资信|履约)\s*(\d+)\s*分'
        )
        for m in cat_pattern.finditer(cat_text):
            result['categories'].append({
                'name': m.group(1),
                'score': int(m.group(2))
            })

    # --- 策略2: 提取管道符表格行 ---
    # 匹配: | 序号 | 评分因素 | 分值 | 评分标准 |
    pipe_items = extract_pipe_table_items(text)
    if pipe_items:
        result['items'].extend(pipe_items)
        result['raw_extraction'] = True

    # --- 策略3: 提取编号评分项 ---
    # 匹配: （1）项目理解（5分）或 1. 项目理解 5分
    numbered_items = extract_numbered_items(text)
    if numbered_items:
        # 去重（避免与管道符表格重复）
        existing_factors = {item['factor'] for item in result['items']}
        for item in numbered_items:
            if item['factor'] not in existing_factors:
                result['items'].append(item)
                result['raw_extraction'] = True

    # --- 策略4: 搜索评审办法前附表区域 ---
    # 找到"评审办法前附表"到下一个章节标题之间的内容
    if not result['items']:
        eval_section = extract_eval_section(text)
        if eval_section:
            # 在评审办法区域内搜索评分项
            section_items = extract_numbered_items(eval_section)
            if section_items:
                result['items'].extend(section_items)
                result['raw_extraction'] = True

    # 为每个评分项分配类别和类型
    for i, item in enumerate(result['items']):
        if not item.get('id'):
            item['id'] = i + 1
        item['category'] = item.get('category') or classify_category(item.get('factor', '') + item.get('criteria_text', ''))
        item['type'] = classify_type(item)

    # 生成说明信息
    if not result['raw_extraction']:
        if result['total_score']:
            result['notes'] = (
                f'已提取总分组架（总分{result["total_score"]}分），'
                f'但未找到详细评分标准表。'
                f'这通常是因为 PDF 表格未被文本提取工具正确解析。'
                f'请使用 --scoring 参数提供评分标准文件，或手动创建。'
            )
        else:
            result['notes'] = (
                '未找到任何评分标准信息。'
                '请使用 --scoring 参数提供评分标准文件。'
            )
    else:
        result['notes'] = f'已自动提取 {len(result["items"])} 个评分项。'

    return result


def extract_pipe_table_items(text):
    """从管道符分隔的表格中提取评分项"""
    items = []
    lines = text.split('\n')

    # 识别评分表头
    in_scoring_table = False
    header_cols = []

    for i, line in enumerate(lines):
        line = line.strip()
        if '|' not in line:
            continue

        cells = [c.strip() for c in line.split('|') if c.strip()]

        # 检测表头
        if not in_scoring_table:
            header_text = ''.join(cells)
            if any(kw in header_text for kw in ['评分因素', '评审因素', '评分项', '评审项']) and \
               any(kw in header_text for kw in ['分值', '分数', '分', '标准']):
                in_scoring_table = True
                header_cols = cells
                continue

        # 表格数据行
        if in_scoring_table:
            # 分隔线跳过
            if all(c.startswith('---') or c.startswith('===') or set(c) <= set('-:=') for c in cells):
                continue

            # 尝试解析评分项
            if len(cells) >= 2:
                item = parse_table_row(cells, header_cols)
                if item:
                    items.append(item)

            # 空行或新表头表示表格结束
            if not cells or (cells and any(kw in cells[0] for kw in ['序号', '类别', '评审类别'])):
                if items:  # 已经收集到数据，说明是新表头
                    in_scoring_table = False
                    header_cols = []

    return items


def parse_table_row(cells, header_cols):
    """解析表格行为评分项"""
    item = {}

    # 尝试根据表头映射
    factor_idx = None
    score_idx = None
    criteria_idx = None
    type_idx = None

    for i, h in enumerate(header_cols):
        h_lower = h.lower()
        if '因素' in h or '项目' in h or '内容' in h:
            factor_idx = i
        elif '分值' in h or '分数' in h or h.strip() == '分':
            score_idx = i
        elif '标准' in h or '说明' in h or '依据' in h or '细则' in h:
            criteria_idx = i
        elif '类别' in h or '类型' in h or '分类' in h:
            type_idx = i

    # 如果没有表头，尝试自动检测
    if factor_idx is None:
        for i, c in enumerate(cells):
            if re.search(r'\d+\s*分', c) and score_idx is None:
                score_idx = i
            elif factor_idx is None and len(c) > 2 and not re.match(r'^\d+$', c):
                factor_idx = i

    # 提取评分因素
    if factor_idx is not None and factor_idx < len(cells):
        item['factor'] = cells[factor_idx]

    # 提取分值
    if score_idx is not None and score_idx < len(cells):
        score_text = cells[score_idx]
        score_match = re.search(r'(\d+(?:\.\d+)?)', score_text)
        if score_match:
            item['score'] = float(score_match.group(1))
    else:
        # 尝试从任何单元格中提取分值
        for c in cells:
            score_match = re.search(r'(\d+(?:\.\d+)?)\s*分', c)
            if score_match:
                item['score'] = float(score_match.group(1))
                break

    # 提取评分标准
    if criteria_idx is not None and criteria_idx < len(cells):
        item['criteria_text'] = cells[criteria_idx]

    # 提取类别
    if type_idx is not None and type_idx < len(cells):
        item['category'] = cells[type_idx]

    # 验证：必须有评分因素或评分标准
    if not item.get('factor') and not item.get('criteria_text'):
        return None

    # 过滤明显不是评分项的行
    if item.get('factor') and any(kw in item['factor'] for kw in ['序号', '合计', '总计', '小计', '说明']):
        return None

    return item


def extract_numbered_items(text):
    """从文本中提取编号评分项"""
    items = []

    # 模式1: （1）项目理解 5分 或 (1)项目理解（5分）
    pattern1 = re.compile(
        r'[（(](\d+)[)）]\s*'
        r'([^（）()5-9\d]{2,30}?)'  # 评分因素名称
        r'(?:[（(](\d+(?:\.\d+)?)\s*分[)）]|(\d+(?:\.\d+)?)\s*分)'
    )

    # 模式2: 1. 项目理解 5分 或 1、项目理解 5分
    pattern2 = re.compile(
        r'(\d+)[.、]\s*'
        r'([^（）()\d]{2,30}?)'
        r'(\d+(?:\.\d+)?)\s*分'
    )

    # 模式3: 项目理解（5分）—— 无编号但有分值
    pattern3 = re.compile(
        r'([\u4e00-\u9fa5]{2,20}?)'
        r'[（(](\d+(?:\.\d+)?)\s*分[)）]'
    )

    used_factors = set()

    for pattern, has_num in [(pattern1, True), (pattern2, True), (pattern3, False)]:
        for match in pattern.finditer(text):
            factor = ''
            score = None
            num = None

            if has_num:
                if pattern == pattern1:
                    num = int(match.group(1))
                    factor = match.group(2).strip()
                    score = float(match.group(3) or match.group(4))
                elif pattern == pattern2:
                    num = int(match.group(1))
                    factor = match.group(2).strip()
                    score = float(match.group(3))
            else:
                factor = match.group(1).strip()
                score = float(match.group(2))

            # 清理评分因素名称
            factor = re.sub(r'[\s:：]+$', '', factor)
            factor = factor.strip('：: ')

            # 跳过明显不是评分因素的
            if len(factor) < 2:
                continue
            if any(skip in factor for skip in ['评审', '总分', '其中', '本项目', '供应商']):
                continue
            if factor in used_factors:
                continue

            # 提取上下文作为评分标准
            match_start = match.start()
            match_end = match.end()
            # 取该行到下一个编号之间的文本作为评分标准
            line_end = text.find('\n', match_end)
            if line_end == -1:
                line_end = min(match_end + 200, len(text))
            criteria_text = text[match_end:line_end].strip()

            item = {
                'factor': factor,
                'score': score,
            }
            if num:
                item['id'] = num
            if criteria_text and len(criteria_text) > 5:
                item['criteria_text'] = criteria_text[:500]

            used_factors.add(factor)
            items.append(item)

    return items


def extract_eval_section(text):
    """提取评审办法前附表区域的内容"""
    # 找到"评审办法前附表"开始位置
    start_patterns = [
        r'评审办法前附表',
        r'评分标准',
        r'详细评审标准',
        r'评审标准',
    ]

    start_pos = -1
    for pattern in start_patterns:
        match = re.search(pattern, text)
        if match:
            start_pos = match.end()
            break

    if start_pos == -1:
        return None

    # 找到下一个主要章节标题
    end_patterns = [
        r'\n第[一二三四五六七八九十]+章',
        r'\n\d+\s*评审方法',
        r'\n\d+\s*评审程序',
        r'\n\d+\s*初步评审',
    ]

    end_pos = len(text)
    for pattern in end_patterns:
        match = re.search(pattern, text[start_pos:])
        if match:
            candidate_end = start_pos + match.start()
            if candidate_end < end_pos:
                end_pos = candidate_end

    return text[start_pos:end_pos]


def classify_category(text):
    """根据文本内容判断评分类别"""
    if not text:
        return '技术'  # 默认归类为技术

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return category

    return '技术'


def classify_type(item):
    """判断评分项是客观分还是主观分"""
    text = (item.get('factor', '') + item.get('criteria_text', ''))

    # 客观分：通过/不通过型
    for kw in OBJECTIVE_KEYWORDS:
        if kw in text:
            return 'objective'

    # 价格分通常是客观分
    if item.get('category') == '价格':
        return 'objective'

    # 其他默认为主观分
    return 'subjective'


def load_scoring_file(scoring_path):
    """从外部文件加载评分标准

    支持格式:
    - JSON: 直接解析为评分项列表
    - Markdown: 解析表格或编号列表
    """
    with open(scoring_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # JSON 格式
    if scoring_path.endswith('.json'):
        try:
            data = json.loads(content)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('items', data.get('scoring_items', []))
                if not items and 'total_score' in data:
                    return data
            else:
                items = []
        except json.JSONDecodeError:
            items = []
    else:
        # Markdown 格式：尝试管道符表格和编号列表
        items = extract_pipe_table_items(content)
        if not items:
            items = extract_numbered_items(content)

    # 为每个项补充字段
    for i, item in enumerate(items):
        if not item.get('id'):
            item['id'] = i + 1
        if not item.get('category'):
            item['category'] = classify_category(
                item.get('factor', '') + item.get('criteria_text', '')
            )
        if not item.get('type'):
            item['type'] = classify_type(item)

    return {
        'total_score': None,
        'categories': [],
        'items': items,
        'raw_extraction': True,
        'notes': f'从外部文件加载 {len(items)} 个评分项'
    }


def parse_tender(tender_path, scoring_path=None, output_dir=None):
    """解析招标文件，提取评分标准

    Args:
        tender_path: 招标文件解析结果路径（Markdown）
        scoring_path: 外部评分标准文件路径（可选）
        output_dir: 输出目录

    Returns:
        dict: 评分标准数据
    """
    # 读取招标文件
    with open(tender_path, 'r', encoding='utf-8') as f:
        tender_text = f.read()

    # 提取评分标准
    if scoring_path:
        print(f'[评分标准] 从外部文件加载: {scoring_path}')
        scoring_data = load_scoring_file(scoring_path)
        # 同时从招标文件中提取总分组架
        auto_data = extract_scoring_from_text(tender_text)
        if auto_data['total_score'] and not scoring_data['total_score']:
            scoring_data['total_score'] = auto_data['total_score']
        if auto_data['categories'] and not scoring_data['categories']:
            scoring_data['categories'] = auto_data['categories']
    else:
        print('[评分标准] 从招标文件中自动提取...')
        scoring_data = extract_scoring_from_text(tender_text)

    # 提取项目信息
    project_info = extract_project_info(tender_text)
    scoring_data['project_info'] = project_info

    # 输出统计
    print(f'[评分标准] 总分: {scoring_data["total_score"] or "未找到"}')
    if scoring_data['categories']:
        cats = ', '.join(f'{c["name"]}{c["score"]}分' for c in scoring_data['categories'])
        print(f'[评分标准] 类别: {cats}')
    print(f'[评分标准] 评分项: {len(scoring_data["items"])} 个')
    if scoring_data['notes']:
        print(f'[评分标准] {scoring_data["notes"]}')

    # 保存 JSON
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, 'eval_criteria.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(scoring_data, f, ensure_ascii=False, indent=2)
        print(f'[输出] {json_path}')

    return scoring_data


def extract_project_info(text):
    """从招标文件中提取项目基本信息"""
    info = {}

    # 项目名称 - 优先从文件开头提取（通常在标题行）
    # 只在文件前500字符内搜索，避免匹配到正文中的内容
    header_text = text[:500]
    # 先尝试从询比公告/招标公告中提取
    name_patterns = [
        # 从开头标题提取: "XXX项目\n询比文件" 或 "XXX项目\n招标文件"
        r'([\u4e00-\u9fa5（）()A-Za-z0-9]{10,80}?)\n(?:询比文件|招标文件|采购文件)',
        # "项目名称：XXX" (排除模板文字)
        r'项目名称[：:]\s*([^\n]{5,80}?)(?:\n|$)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, header_text, re.MULTILINE)
        if match:
            candidate = match.group(1).strip()
            # 排除模板文字和无意义内容
            if '见供应商须知' not in candidate and '见前附表' not in candidate \
               and '参与' not in candidate and '各方' not in candidate and len(candidate) > 5:
                info['project_name'] = candidate
                break

    # 项目编号
    code_match = re.search(r'项目编号[：:]\s*(\S+)', text)
    if code_match:
        info['project_code'] = code_match.group(1).strip()

    # 采购人
    buyer_match = re.search(r'采购人[：:]\s*([^\n]{3,40}?)(?:\n|$)', text)
    if buyer_match:
        candidate = buyer_match.group(1).strip()
        if '见' not in candidate and len(candidate) > 2:
            info['buyer'] = candidate

    # 最高限价
    price_match = re.search(r'最高响应限价[为是]?[^，。]*?(\d+(?:,\d{3})*(?:\.\d+)?)\s*元', text)
    if price_match:
        info['max_price'] = price_match.group(1)

    return info


# ============================================================
# 评分项映射
# ============================================================

def load_outline(outline_path):
    """从大纲文件中加载章节结构

    支持:
    - Markdown 标题（# ## ### ####）
    - JSON 格式（chapter列表）
    """
    with open(outline_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if outline_path.endswith('.json'):
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return data.get('chapters', data.get('outline', []))

    # 解析 Markdown 标题
    chapters = []
    for line in content.split('\n'):
        line = line.rstrip()
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            title = line.lstrip('#').strip()
            if title:
                chapters.append({
                    'level': level,
                    'title': title,
                })

    return chapters


def map_eval_to_chapters(scoring_data, outline_chapters):
    """将评分项映射到章节

    使用关键词匹配策略:
    1. 评分因素关键词 → 章节标题关键词
    2. 评分标准文本关键词 → 章节标题关键词
    3. 类别匹配（商务/技术/价格）

    Returns:
        list: 映射结果列表
    """
    mappings = []

    for item in scoring_data.get('items', []):
        factor = item.get('factor', '')
        criteria = item.get('criteria_text', '')
        category = item.get('category', '技术')
        item_id = item.get('id', '')
        score = item.get('score', '')

        # 计算与每个章节的匹配度
        best_matches = []

        for ch in outline_chapters:
            ch_title = ch.get('title', '')
            ch_level = ch.get('level', 1)

            # 跳过过深的章节（level > 4 通常不需要映射）
            if ch_level > 4:
                continue

            # 跳过明显不是方案章节的标题
            if any(skip in ch_title for skip in ['封面', '索引表', '证明', '身份证', '学历',
                                                   '社保', '证书证明', '合同复印件', '发票',
                                                   '盖章', '签字', '日期', '编制要求']):
                continue

            match_score = calculate_match_score(factor, criteria, ch_title)

            if match_score > 0:
                best_matches.append({
                    'chapter': ch_title,
                    'level': ch_level,
                    'match_score': match_score,
                })

        # 按匹配度排序，取前3个
        best_matches.sort(key=lambda x: x['match_score'], reverse=True)
        top_matches = best_matches[:3]

        # 确定映射状态
        if top_matches and top_matches[0]['match_score'] >= 5:
            status = '已映射'
            suggested_chapter = top_matches[0]['chapter']
        elif top_matches and top_matches[0]['match_score'] >= 2:
            status = '建议映射'
            suggested_chapter = top_matches[0]['chapter']
        else:
            status = '未映射'
            suggested_chapter = ''

        mapping = {
            'id': item_id,
            'factor': factor,
            'category': category,
            'score': score,
            'type': item.get('type', 'subjective'),
            'suggested_chapter': suggested_chapter,
            'status': status,
            'all_matches': top_matches,
            'criteria_text': criteria[:200] if criteria else '',
        }
        mappings.append(mapping)

    return mappings


def calculate_match_score(factor, criteria, chapter_title):
    """计算评分项与章节标题的匹配度

    匹配规则:
    - 评分因素直接出现在章节标题中: +5
    - 评分因素关键词出现在章节标题中: +3
    - 评分标准文本关键词出现在章节标题中: +1
    - 章节标题关键词出现在评分标准中: +1
    """
    score = 0

    if not factor and not criteria:
        return 0

    # 1. 评分因素直接出现在章节标题中
    if factor and factor in chapter_title:
        score += 5

    # 2. 评分因素关键词匹配
    if factor:
        factor_keywords = get_factor_keywords(factor)
        for kw in factor_keywords:
            if kw in chapter_title:
                score += 3
                break  # 只加一次

    # 3. 评分标准文本关键词出现在章节标题中
    if criteria:
        # 提取评分标准中的关键短语
        criteria_keywords = extract_keywords(criteria)
        for kw in criteria_keywords:
            if len(kw) >= 3 and kw in chapter_title:
                score += 1
                break  # 只加一次

    # 4. 章节标题关键词出现在评分因素/标准中
    ch_keywords = extract_keywords(chapter_title)
    for kw in ch_keywords:
        if len(kw) >= 3 and (kw in factor or kw in criteria):
            score += 1
            break  # 只加一次

    return score


def get_factor_keywords(factor):
    """获取评分因素对应的关键词列表"""
    keywords = []

    # 先查预设映射
    for key, values in FACTOR_TO_CHAPTER_KEYWORDS.items():
        if key in factor:
            keywords.extend(values)
            break

    # 补充：因素本身的关键词
    if len(factor) >= 3:
        keywords.append(factor)

    return keywords


def extract_keywords(text):
    """从文本中提取关键词（简单的中文分词）"""
    if not text:
        return []

    keywords = []
    # 提取2-6字的中文词组
    pattern = re.compile(r'[\u4e00-\u9fa5]{2,6}')
    matches = pattern.findall(text)

    # 过滤停用词
    stop_words = {'的', '了', '和', '与', '及', '或', '在', '为', '对', '按', '向',
                  '进行', '提供', '根据', '按照', '要求', '应该', '应当', '可以',
                  '满足', '供应商', '响应', '项目', '内容', '标准', '因素'}

    for m in matches:
        if m not in stop_words and m not in keywords:
            keywords.append(m)

    return keywords


# ============================================================
# 覆盖检查
# ============================================================

def check_coverage(mappings):
    """检查评分项覆盖情况

    Returns:
        dict: 覆盖统计
    """
    total = len(mappings)
    mapped = sum(1 for m in mappings if m['status'] == '已映射')
    suggested = sum(1 for m in mappings if m['status'] == '建议映射')
    unmapped = sum(1 for m in mappings if m['status'] == '未映射')

    # 按类别统计
    by_category = {}
    for m in mappings:
        cat = m.get('category', '技术')
        if cat not in by_category:
            by_category[cat] = {'total': 0, 'mapped': 0, 'unmapped': 0}
        by_category[cat]['total'] += 1
        if m['status'] == '已映射':
            by_category[cat]['mapped'] += 1
        elif m['status'] == '未映射':
            by_category[cat]['unmapped'] += 1

    # 未映射的评分项
    unmapped_items = [m for m in mappings if m['status'] == '未映射']

    return {
        'total': total,
        'mapped': mapped,
        'suggested': suggested,
        'unmapped': unmapped,
        'coverage_rate': f'{mapped / total * 100:.1f}%' if total > 0 else '0%',
        'by_category': by_category,
        'unmapped_items': unmapped_items,
    }


# ============================================================
# 报告生成
# ============================================================

def generate_mapping_report(scoring_data, mappings, coverage):
    """生成评分点映射表 Markdown 报告"""
    lines = []
    lines.append('# 评分点映射表')
    lines.append('')
    lines.append(f'> 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    lines.append('')

    # 项目信息
    project_info = scoring_data.get('project_info', {})
    if project_info:
        lines.append('## 项目信息')
        lines.append('')
        for key, label in [('project_name', '项目名称'), ('project_code', '项目编号'),
                           ('buyer', '采购人'), ('max_price', '最高限价')]:
            if project_info.get(key):
                lines.append(f'- **{label}**: {project_info[key]}')
        lines.append('')

    # 总分信息
    lines.append('## 评分总览')
    lines.append('')
    if scoring_data.get('total_score'):
        lines.append(f'- **总分**: {scoring_data["total_score"]}分')
    if scoring_data.get('categories'):
        cats = '、'.join(f'{c["name"]}{c["score"]}分' for c in scoring_data['categories'])
        lines.append(f'- **分值分布**: {cats}')
    lines.append(f'- **评分项总数**: {coverage["total"]}')
    lines.append(f'- **已映射**: {coverage["mapped"]} ({coverage["coverage_rate"]})')
    lines.append(f'- **建议映射**: {coverage["suggested"]}')
    lines.append(f'- **未映射**: {coverage["unmapped"]}')
    lines.append('')

    # 按类别统计
    if coverage.get('by_category'):
        lines.append('### 按类别统计')
        lines.append('')
        lines.append('| 类别 | 总数 | 已映射 | 未映射 | 覆盖率 |')
        lines.append('|------|------|--------|--------|--------|')
        for cat, stats in sorted(coverage['by_category'].items()):
            rate = f'{stats["mapped"] / stats["total"] * 100:.0f}%' if stats['total'] > 0 else '0%'
            lines.append(f'| {cat} | {stats["total"]} | {stats["mapped"]} | {stats["unmapped"]} | {rate} |')
        lines.append('')

    # 详细映射表
    lines.append('## 评分项映射详情')
    lines.append('')
    lines.append('| 序号 | 类别 | 评分因素 | 分值 | 类型 | 建议章节 | 状态 |')
    lines.append('|------|------|----------|------|------|----------|------|')

    for m in mappings:
        status_icon = {
            '已映射': '✅',
            '建议映射': '⚠️',
            '未映射': '❌',
        }.get(m['status'], m['status'])

        chapter = m['suggested_chapter'] or '—'
        if len(chapter) > 30:
            chapter = chapter[:28] + '...'

        factor = m['factor'] or '—'
        if len(factor) > 20:
            factor = factor[:18] + '...'

        score = m['score'] if m['score'] is not None else '—'
        type_label = '客观' if m.get('type') == 'objective' else '主观'

        lines.append(f'| {m["id"]} | {m["category"]} | {factor} | {score} | {type_label} | {chapter} | {status_icon} |')

    lines.append('')

    # 未映射项详情
    if coverage.get('unmapped_items'):
        lines.append('## 未映射评分项详情')
        lines.append('')
        lines.append('以下评分项未能自动映射到章节，需要人工分析:')
        lines.append('')
        for m in coverage['unmapped_items']:
            lines.append(f'### {m["id"]}. {m["factor"]} ({m["score"]}分)')
            lines.append(f'- 类别: {m["category"]}')
            if m.get('criteria_text'):
                lines.append(f'- 评分标准: {m["criteria_text"]}')
            lines.append(f'- **需手动指定对应章节**')
            lines.append('')

    # 评分标准原文（如有）
    if scoring_data.get('notes'):
        lines.append('## 提取说明')
        lines.append('')
        lines.append(scoring_data['notes'])
        lines.append('')

    # 字数分配建议
    if scoring_data.get('total_score') and scoring_data.get('categories'):
        lines.append('## 字数分配建议')
        lines.append('')
        lines.append(f'根据评分分值分配各章节字数（以400页为基准，780字/页，总分{scoring_data["total_score"]}分）:')
        lines.append('')
        lines.append('| 评分项 | 类别 | 分值 | 建议字数 | 合格范围 |')
        lines.append('|--------|------|------|----------|----------|')
        for m in mappings:
            # 价格分不参与字数分配
            if m.get('category') == '价格':
                continue
            if m.get('score') and scoring_data.get('total_score'):
                total_score = scoring_data['total_score']
                target_words = int(m['score'] * (400 / total_score) * 780)
                min_words = int(target_words * 0.75)
                max_words = int(target_words * 1.25)
                factor = m['factor'] or f'项{m["id"]}'
                lines.append(f'| {factor} | {m["category"]} | {m["score"]}分 | {target_words:,}字 | {min_words:,}~{max_words:,}字 |')
        lines.append('')
        lines.append('> 注意：价格分不参与字数分配，报价得分按公式计算。')
        lines.append('> 实际总页数请根据用户指定的目标页数调整。')
        lines.append('')

    # 商务项说明
    commercial_items = [m for m in mappings if m.get('category') == '商务' and m['status'] == '未映射']
    if commercial_items:
        lines.append('## 商务评分项说明')
        lines.append('')
        lines.append('以下商务评分项在技术标大纲中未找到对应章节，这通常属于正常情况。')
        lines.append('商务评分项一般在商务响应文件中回应，不在技术标中编写。')
        lines.append('')
        for m in commercial_items:
            lines.append(f'- **{m["factor"]}** ({m["score"]}分): {m.get("criteria_text", "")}')
        lines.append('')

    return '\n'.join(lines)


def generate_json_output(scoring_data, mappings, coverage):
    """生成完整的 JSON 输出"""
    return {
        'project_info': scoring_data.get('project_info', {}),
        'total_score': scoring_data.get('total_score'),
        'categories': scoring_data.get('categories', []),
        'items': scoring_data.get('items', []),
        'mappings': mappings,
        'coverage': coverage,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'notes': scoring_data.get('notes', ''),
    }


# ============================================================
# 主函数
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'parse':
        if len(sys.argv) < 3:
            print('用法: eval_mapping.py parse <招标文件.md> [--output <目录>] [--scoring <文件>]')
            sys.exit(1)

        tender_path = sys.argv[2]
        output_dir = None
        scoring_path = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--output' and i + 1 < len(args):
                output_dir = args[i + 1]; i += 2
            elif args[i] == '--scoring' and i + 1 < len(args):
                scoring_path = args[i + 1]; i += 2
            else:
                i += 1

        parse_tender(tender_path, scoring_path, output_dir)

    elif cmd == 'map':
        if len(sys.argv) < 3:
            print('用法: eval_mapping.py map <eval_criteria.json> --outline <大纲.md> [--output <目录>]')
            sys.exit(1)

        criteria_path = sys.argv[2]
        outline_path = None
        output_dir = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--outline' and i + 1 < len(args):
                outline_path = args[i + 1]; i += 2
            elif args[i] == '--output' and i + 1 < len(args):
                output_dir = args[i + 1]; i += 2
            else:
                i += 1

        if not outline_path:
            print('错误: 必须指定 --outline 参数')
            sys.exit(1)

        # 加载数据
        with open(criteria_path, 'r', encoding='utf-8') as f:
            scoring_data = json.load(f)

        outline_chapters = load_outline(outline_path)
        print(f'[大纲] 加载 {len(outline_chapters)} 个章节')

        # 映射
        mappings = map_eval_to_chapters(scoring_data, outline_chapters)
        coverage = check_coverage(mappings)

        print(f'[映射] 总计 {coverage["total"]} 项, 已映射 {coverage["mapped"]}, 未映射 {coverage["unmapped"]}')

        # 生成报告
        report = generate_mapping_report(scoring_data, mappings, coverage)
        full_json = generate_json_output(scoring_data, mappings, coverage)

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            md_path = os.path.join(output_dir, '评分点映射表.md')
            json_path = os.path.join(output_dir, 'eval_mapping_result.json')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(report)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(full_json, f, ensure_ascii=False, indent=2)
            print(f'[输出] {md_path}')
            print(f'[输出] {json_path}')
        else:
            print(report)

    elif cmd == 'check':
        if len(sys.argv) < 3:
            print('用法: eval_mapping.py check <eval_criteria.json> --outline <大纲.md>')
            sys.exit(1)

        criteria_path = sys.argv[2]
        outline_path = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--outline' and i + 1 < len(args):
                outline_path = args[i + 1]; i += 2
            else:
                i += 1

        if not outline_path:
            print('错误: 必须指定 --outline 参数')
            sys.exit(1)

        with open(criteria_path, 'r', encoding='utf-8') as f:
            scoring_data = json.load(f)

        outline_chapters = load_outline(outline_path)
        mappings = map_eval_to_chapters(scoring_data, outline_chapters)
        coverage = check_coverage(mappings)

        print(f'覆盖检查结果:')
        print(f'  总计: {coverage["total"]} 项')
        print(f'  已映射: {coverage["mapped"]} ({coverage["coverage_rate"]})')
        print(f'  建议映射: {coverage["suggested"]}')
        print(f'  未映射: {coverage["unmapped"]}')
        if coverage['unmapped_items']:
            print(f'\n未映射的评分项:')
            for m in coverage['unmapped_items']:
                print(f'  - [{m["id"]}] {m["factor"]} ({m["score"]}分) — {m["category"]}')

    elif cmd == 'report':
        if len(sys.argv) < 3:
            print('用法: eval_mapping.py report <招标文件.md> --outline <大纲.md> [--output <目录>] [--scoring <文件>]')
            sys.exit(1)

        tender_path = sys.argv[2]
        outline_path = None
        output_dir = None
        scoring_path = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--outline' and i + 1 < len(args):
                outline_path = args[i + 1]; i += 2
            elif args[i] == '--output' and i + 1 < len(args):
                output_dir = args[i + 1]; i += 2
            elif args[i] == '--scoring' and i + 1 < len(args):
                scoring_path = args[i + 1]; i += 2
            else:
                i += 1

        if not outline_path:
            print('错误: 必须指定 --outline 参数')
            sys.exit(1)

        if not output_dir:
            output_dir = os.path.dirname(tender_path) or '.'

        # Step 1: 解析评分标准
        print('=' * 60)
        print('Step 1: 解析评分标准')
        print('=' * 60)
        scoring_data = parse_tender(tender_path, scoring_path, output_dir)

        # Step 2: 映射到章节
        print()
        print('=' * 60)
        print('Step 2: 映射到章节大纲')
        print('=' * 60)
        outline_chapters = load_outline(outline_path)
        print(f'[大纲] 加载 {len(outline_chapters)} 个章节')
        mappings = map_eval_to_chapters(scoring_data, outline_chapters)
        coverage = check_coverage(mappings)
        print(f'[映射] 总计 {coverage["total"]} 项, 已映射 {coverage["mapped"]}, 未映射 {coverage["unmapped"]}')

        # Step 3: 生成报告
        print()
        print('=' * 60)
        print('Step 3: 生成报告')
        print('=' * 60)
        report = generate_mapping_report(scoring_data, mappings, coverage)
        full_json = generate_json_output(scoring_data, mappings, coverage)

        md_path = os.path.join(output_dir, '评分点映射表.md')
        json_path = os.path.join(output_dir, 'eval_mapping_result.json')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(report)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(full_json, f, ensure_ascii=False, indent=2)
        print(f'[输出] {md_path}')
        print(f'[输出] {json_path}')
        print(f'[完成] 评分点映射报告已生成')

    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
