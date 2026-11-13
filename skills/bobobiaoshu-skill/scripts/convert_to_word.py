#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Markdown转Word技术标文档 - 转换脚本 v6.0
支持基于模板生成 Word 文档，完整继承模板的样式

## v6.0 重大更新
1. 支持以 .docx 模板为基础生成文档，完整继承模板样式
2. 自动从模板提取 Normal/Heading 样式参数
3. 无模板时仍支持 doc-format 注释块配置

## 用法
    # 基于模板生成（推荐）
    python convert_to_word.py <输入.md> <输出.docx> --template <模板.docx>

    # 无模板，使用默认或 doc-format 注释块
    python convert_to_word.py <输入.md> <输出.docx>

    # 指定格式参数
    python convert_to_word.py <输入.md> <输出.docx> --font SimSun --body-size 12 --line-spacing 1.5
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
import sys
import os
import re
import json
import copy

# 跨平台兼容：字体映射
try:
    from macos_compat import get_font, get_default_font, adapt_font_dict, is_macos
except ImportError:
    def get_font(name): return name
    def get_default_font(): return '宋体'
    def adapt_font_dict(fmt): return fmt
    def is_macos(): return sys.platform == 'darwin'

# 默认格式参数（与用户模板一致）
DEFAULT_FORMAT = {
    'font': '宋体',
    'east_asia_font': '宋体',
    'body-size': 12,        # pt (小四)
    'title-size': 15,       # pt (H1)
    'h2-size': 14,          # pt
    'h3-size': 12,          # pt
    'h4-size': 11,          # pt
    'line-spacing': 1.5,    # 倍行距
    'line-spacing-rule': 'ONE_POINT_FIVE',
    'margins': 2.54,        # cm (上下)
    'margins-lr': 3.17,     # cm (左右)
    'first-line-indent': 0.74,  # cm
    'page-width': 21,       # cm
    'page-height': 29.7,    # cm
    'header-distance': 1.5, # cm
    'footer-distance': 1.75,# cm
    'space-before-h1': 16,  # pt
    'space-after-h1': 16,   # pt
    'space-before-h2': 14,
    'space-after-h2': 14,
    'space-before-h3': 12,
    'space-after-h3': 12,
}


def parse_pt(value):
    """解析 pt 值"""
    s = str(value).strip()
    if s.endswith('pt'):
        s = s[:-2]
    try:
        return float(s)
    except:
        return None


def parse_cm(value):
    """解析 cm 值"""
    s = str(value).strip()
    if s.endswith('cm'):
        s = s[:-2]
    try:
        return float(s)
    except:
        return None


def strip_heading_number(text):
    """去除标题中的编号文本，只保留标题名称

    模板已定义自动编号（decimal: 1 / 1.1 / 1.1.1），
    如果标题中包含编号文本会导致叠加（如 "1. 一、概述"）。
    此函数剥离编号，让模板的 numPr 自动管理。

    支持的编号格式：
    - 中文数字：一、二、三、…
    - 十进制：1. / 1.1 / 1.1.1 / 1.1.1.1
    - 括号编号：（1） / (1)
    - 中文顿号：一、 / 1．
    - 空格编号：1 概述 / 1.1 编制目的
    """
    s = text.strip()

    # 中文数字编号：一、二、… + 顿号/点
    s = re.sub(r'^[一二三四五六七八九十百千]+[、．.．]\s*', '', s)
    # 十进制编号：1. / 1.1 / 1.1.1 / 1.1.1.1 + 可选空格/点
    s = re.sub(r'^\d+(?:\.\d+)*[.．、]?\s+', '', s)
    # 括号编号：（1）或 (1)
    s = re.sub(r'^[（(]\d+[）)]\s*', '', s)
    # 纯数字 + 空格：1 概述
    s = re.sub(r'^\d+\s+', '', s)

    return s.strip()


def clean_heading_text(text):
    """清理标题：去编号文本 + 去描述性括号"""
    # 1. 去编号文本
    result = strip_heading_number(text.strip())
    # 2. 去描述性括号
    patterns = [
        r'（深入[^）]*）', r'（详细[^）]*）', r'（扩展[^）]*）',
        r'（进一步[^）]*）', r'（补充[^）]*）', r'（说明[^）]*）',
        r'\(深入[^)]*\)', r'\(详细[^)]*\)', r'\(扩展[^)]*\)',
    ]
    for pattern in patterns:
        result = re.sub(pattern, '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def parse_format_block(content):
    """从 Markdown 内容中解析 doc-format 格式指令"""
    fmt = DEFAULT_FORMAT.copy()
    pattern = r'<!--\s*doc-format\s*([\s\S]*?)-->'
    match = re.search(pattern, content)
    if not match:
        return fmt, content

    block = match.group(1)
    content = re.sub(pattern, '', content, count=1).strip()

    for line in block.split('\n'):
        line = line.strip()
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        key = key.strip().lower()
        value = value.strip()

        if key == 'font':
            fmt['font'] = value
            fmt['east_asia_font'] = value
        elif key == 'body-size':
            v = parse_pt(value)
            if v: fmt['body-size'] = v
        elif key == 'title-level':
            v = parse_pt(value)
            if v: fmt['title-size'] = v
        elif key == 'sub-level':
            v = parse_pt(value)
            if v: fmt['h2-size'] = v
        elif key == 'line-spacing':
            v = parse_pt(value)
            if v: fmt['line-spacing'] = v
        elif key == 'margins':
            v = parse_cm(value)
            if v:
                fmt['margins'] = v
                fmt['margins-lr'] = v
        elif key == 'first-line-indent':
            v = parse_cm(value)
            if v: fmt['first-line-indent'] = v

    return fmt, content


def extract_template_styles(template_path):
    """从模板文档提取样式参数

    优先级：正文1/正文 > Normal 用于正文格式
    """
    from docx import Document as DocxDocument

    tdoc = DocxDocument(template_path)
    fmt = {}

    # 页面设置
    for section in tdoc.sections:
        fmt['page-width'] = round(section.page_width.cm, 2)
        fmt['page-height'] = round(section.page_height.cm, 2)
        fmt['margins'] = round(section.top_margin.cm, 2)
        fmt['margins-lr'] = round(section.left_margin.cm, 2)
        if section.header_distance:
            fmt['header-distance'] = round(section.header_distance.cm, 2)
        if section.footer_distance:
            fmt['footer-distance'] = round(section.footer_distance.cm, 2)
        break

    # 先收集所有相关样式
    normal_info = {}
    body_text_info = {}  # 正文1 等自定义正文样式

    for style in tdoc.styles:
        if style.type is None or not style.name:
            continue
        try:
            font = style.font
            pf = style.paragraph_format
            name = style.name

            def _extract_style_info(font, pf):
                info = {}
                if font.name:
                    info['font'] = font.name
                if font.size:
                    info['size_pt'] = font.size.pt
                # 检查东亚字体
                rPr = font.element.find(qn('w:rPr')) if hasattr(font, 'element') else None
                if rPr is not None:
                    rFonts = rPr.find(qn('w:rFonts'))
                    if rFonts is not None:
                        east = rFonts.get(qn('w:eastAsia'))
                        if east:
                            info['east_asia_font'] = east
                if pf:
                    if pf.first_line_indent:
                        info['first_line_indent_cm'] = round(pf.first_line_indent.cm, 2)
                    if pf.line_spacing:
                        info['line_spacing'] = pf.line_spacing
                    if pf.space_before:
                        info['space_before_pt'] = pf.space_before.pt
                    if pf.space_after:
                        info['space_after_pt'] = pf.space_after.pt
                return info

            if name == 'Normal':
                normal_info = _extract_style_info(font, pf)
            elif name in ('正文1', '正文'):
                body_text_info = _extract_style_info(font, pf)
            elif name == 'Heading 1':
                if font.size:
                    fmt['title-size'] = font.size.pt
                if pf:
                    if pf.space_before:
                        fmt['space-before-h1'] = pf.space_before.pt
                    if pf.space_after:
                        fmt['space-after-h1'] = pf.space_after.pt
            elif name == 'Heading 2':
                if font.size:
                    fmt['h2-size'] = font.size.pt
                if pf:
                    if pf.space_before:
                        fmt['space-before-h2'] = pf.space_before.pt
                    if pf.space_after:
                        fmt['space-after-h2'] = pf.space_after.pt
            elif name == 'Heading 3':
                if font.size:
                    fmt['h3-size'] = font.size.pt
            elif name == 'Heading 4':
                if font.size:
                    fmt['h4-size'] = font.size.pt
        except:
            continue

    # 正文样式合并：优先使用"正文1"，其次 Normal
    # Normal 提供基础字体字号
    if normal_info:
        if 'font' in normal_info:
            fmt['font'] = normal_info['font']
        if 'east_asia_font' in normal_info:
            fmt['east_asia_font'] = normal_info['east_asia_font']
        if 'size_pt' in normal_info:
            fmt['body-size'] = normal_info['size_pt']

    # 正文1 覆盖行距和缩进（如果有）
    if body_text_info:
        if 'font' in body_text_info:
            fmt['font'] = body_text_info['font']
        if 'east_asia_font' in body_text_info:
            fmt['east_asia_font'] = body_text_info['east_asia_font']
        if 'size_pt' in body_text_info:
            fmt['body-size'] = body_text_info['size_pt']
        if 'line_spacing' in body_text_info:
            fmt['line-spacing'] = body_text_info['line_spacing']
        if 'first_line_indent_cm' in body_text_info:
            fmt['first-line-indent'] = body_text_info['first_line_indent_cm']
    else:
        # 没有 正文1，从 Normal 获取
        if 'line_spacing' in normal_info:
            fmt['line-spacing'] = normal_info['line_spacing']
        if 'first_line_indent_cm' in normal_info:
            fmt['first-line-indent'] = normal_info['first_line_indent_cm']
        # Normal 没有首行缩进时使用默认值
        if 'first-line-indent' not in fmt:
            fmt['first-line-indent'] = 0.74

    return fmt


def set_cell_shading(cell, fill_color="FFFFFF"):
    """设置单元格背景色"""
    tcPr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement('w:shd')
    shading.set(qn('w:val'), 'clear')
    shading.set(qn('w:color'), 'auto')
    shading.set(qn('w:fill'), fill_color)
    tcPr.append(shading)


def set_table_border(table):
    """设置表格边框"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)

    tblBorders = OxmlElement('w:tblBorders')
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), '000000')
        tblBorders.append(border)
    tblPr.append(tblBorders)


def parse_markdown_table(line, lines, start_idx):
    """解析Markdown表格"""
    headers = [h.strip() for h in line.split('|') if h.strip()]

    align_line = lines[start_idx + 1] if start_idx + 1 < len(lines) else ""
    alignments = []
    for cell in align_line.split('|'):
        cell = cell.strip()
        if cell.startswith(':') and cell.endswith(':'):
            alignments.append('center')
        elif cell.endswith(':'):
            alignments.append('right')
        else:
            alignments.append('left')

    data_start = start_idx + 2
    rows_data = []
    for i in range(data_start, len(lines)):
        l = lines[i].strip()
        if not l or not l.startswith('|'):
            return headers, alignments, rows_data, i
        row = [c.strip() for c in l.split('|') if c.strip()]
        rows_data.append(row)

    return headers, alignments, rows_data, len(lines)


def _set_cell_para_format(para):
    """设置表格单元格段落的段落格式

    字体字号与模板正文一致（由 set_run_font 处理），
    但段落格式必须独立于正文样式，避免被 Normal 样式的
    首行缩进、行距、段前段后间距带偏导致表格错位。
    """
    pf = para.paragraph_format
    # 清除首行缩进——正文的首行缩进不应作用于表格单元格
    pf.first_line_indent = None
    # 段前段后归零——表格行间距由行高控制，不需要额外段间距
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    # 行距设为单倍行距——表格内使用紧凑行距，不继承正文的 1.5 倍行距
    pf.line_spacing = 1.0
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE


def add_table(doc, headers, alignments, rows, fmt):
    """添加表格

    表格格式规则：
    - 字体字号：与模板正文一致（通过 set_run_font 设置）
    - 段落格式：独立于正文样式，不继承 Normal 的首行缩进/行距/段间距，
      避免正文段落格式带偏导致表格内容错位
    """
    if not headers:
        return None

    col_count = len(headers)
    table = doc.add_table(rows=len(rows) + 1, cols=col_count)
    set_table_border(table)

    font_name = fmt.get('font', '宋体')
    body_size = fmt.get('body-size', 12)

    def set_run_font(run, bold=False):
        run.font.name = font_name
        run.font.size = Pt(body_size)
        run.font.bold = bold
        r = run._element
        rPr = r.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn('w:eastAsia'), fmt.get('east_asia_font', font_name))
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)

    # 表头
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        para = cell.paragraphs[0]
        _set_cell_para_format(para)
        run = para.add_run(h)
        set_run_font(run, bold=True)
        set_cell_shading(cell, "D9E2F3")

        align = alignments[i] if i < len(alignments) else 'left'
        if align == 'center':
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == 'right':
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # 数据行
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            if c_idx >= col_count:
                break
            cell = table.rows[r_idx + 1].cells[c_idx]
            para = cell.paragraphs[0]
            _set_cell_para_format(para)
            run = para.add_run(str(val))
            set_run_font(run)

            align = alignments[c_idx] if c_idx < len(alignments) else 'left'
            if align == 'center':
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif align == 'right':
                para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    return table


def set_heading_style(para, level):
    """设置标题大纲级别和自动编号

    当段落使用 Heading N 样式时，模板可能未在样式级别关联 numPr，
    需要在段落级别注入 numPr 以激活自动编号。
    同时设置 outlineLvl 作为大纲级别标记。
    """
    pPr = para._element.get_or_add_pPr()

    # 设置大纲级别
    existing_outline = pPr.find(qn('w:outlineLvl'))
    if existing_outline is None:
        outlineLvl = OxmlElement('w:outlineLvl')
        outlineLvl.set(qn('w:val'), str(level - 1))
        pPr.append(outlineLvl)

    # 注入自动编号 numPr（使用 numId=1）
    # 模板的 numbering.xml 中定义了 numId=1（decimal 多级编号）
    # 如果样式级别已有 numPr 则跳过，避免重复
    style_numPr = None
    if para.style and para.style.element is not None:
        style_pPr = para.style.element.find(qn('w:pPr'))
        if style_pPr is not None:
            style_numPr = style_pPr.find(qn('w:numPr'))

    if style_numPr is None:
        # 样式没有 numPr，在段落级别注入
        existing_numPr = pPr.find(qn('w:numPr'))
        if existing_numPr is None:
            numPr = OxmlElement('w:numPr')
            ilvl = OxmlElement('w:ilvl')
            ilvl.set(qn('w:val'), str(level - 1))
            numId = OxmlElement('w:numId')
            numId.set(qn('w:val'), '1')
            numPr.append(ilvl)
            numPr.append(numId)
            pPr.append(numPr)


def make_run_with_font(para, text, fmt, size=None, bold=False):
    """创建带字体设置的 run

    对于 Heading 样式段落，不设置字号和加粗（让样式继承），
    仅设置字体名称和颜色，避免 run 级别冗余覆盖。
    """
    font_name = fmt.get('font', '宋体')
    east_asia = fmt.get('east_asia_font', font_name)
    is_heading = para.style and para.style.name.startswith('Heading')

    run = para.add_run(text)
    run.font.name = font_name

    # Heading 段落：字号/加粗由样式定义，不在 run 级覆盖
    if is_heading:
        pass  # 不设置 size 和 bold，继承样式
    else:
        if size:
            run.font.size = Pt(size)
        else:
            run.font.size = Pt(fmt.get('body-size', 12))
        run.font.bold = bold

    run.font.color.rgb = RGBColor(0, 0, 0)

    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn('w:eastAsia'), east_asia)
    rFonts.set(qn('w:ascii'), font_name)
    rFonts.set(qn('w:hAnsi'), font_name)

    return run


def convert_md_to_word(input_md_path, output_docx_path, template_path=None, fmt_override=None):
    """将Markdown文件转换为Word文档

    Args:
        input_md_path: 输入 Markdown 文件路径
        output_docx_path: 输出 Word 文件路径
        template_path: 模板 .docx 文件路径（可选）
        fmt_override: 格式参数覆盖字典（可选）
    """

    if not os.path.exists(input_md_path):
        print(f'错误：输入文件不存在：{input_md_path}')
        return False

    with open(input_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析 doc-format 注释块
    fmt, content = parse_format_block(content)

    # 如果有模板，从模板提取样式覆盖默认值
    if template_path and os.path.exists(template_path):
        print(f'使用模板: {template_path}')
        template_fmt = extract_template_styles(template_path)
        fmt.update(template_fmt)

    # 跨平台字体映射（macOS 上将宋体映射为 Songti SC 等）
    fmt = adapt_font_dict(fmt)

    # 应用命令行覆盖参数
    if fmt_override:
        fmt.update(fmt_override)

    print(f'格式参数: 字体={fmt.get("font", "N/A")} | 正文={fmt.get("body-size", "N/A")}pt'
          f' | 行距={fmt.get("line-spacing", "N/A")} | 边距={fmt.get("margins", "N/A")}cm')

    # 创建文档：优先基于模板
    if template_path and os.path.exists(template_path):
        doc = Document(template_path)
        # 清空模板中的现有内容（保留样式定义）
        # 删除所有现有段落
        body = doc.element.body
        for child in list(body):
            if child.tag.endswith('}sectPr'):
                continue  # 保留页面设置
            body.remove(child)
    else:
        doc = Document()

    # 设置页面
    for section in doc.sections:
        section.top_margin = Cm(fmt.get('margins', 2.54))
        section.bottom_margin = Cm(fmt.get('margins', 2.54))
        section.left_margin = Cm(fmt.get('margins-lr', fmt.get('margins', 3.17)))
        section.right_margin = Cm(fmt.get('margins-lr', fmt.get('margins', 3.17)))
        section.page_height = Cm(fmt.get('page-height', 29.7))
        section.page_width = Cm(fmt.get('page-width', 21))
        if fmt.get('header-distance'):
            section.header_distance = Cm(fmt['header-distance'])
        if fmt.get('footer-distance'):
            section.footer_distance = Cm(fmt['footer-distance'])

    lines = content.split('\n')
    i = 0
    in_code_block = False
    code_lines = []

    while i < len(lines):
        line = lines[i]

        # 处理代码块
        if line.strip().startswith('```'):
            if in_code_block:
                para = doc.add_paragraph()
                make_run_with_font(para, '\n'.join(code_lines), fmt)
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 处理表格
        if line.strip().startswith('|') and '---' not in line:
            headers, alignments, rows_data, end_idx = parse_markdown_table(line, lines, i)
            if headers and rows_data:
                add_table(doc, headers, alignments, rows_data, fmt)
                i = end_idx
                continue

        # 处理标题
        if line.startswith('# '):
            para = doc.add_paragraph(style='Heading 1')
            text = clean_heading_text(line[2:])
            make_run_with_font(para, text, fmt, size=fmt.get('title-size', 15), bold=True)
            set_heading_style(para, 1)
            _apply_heading_spacing(para, fmt, 'h1')
            _clear_heading_indent(para)
        elif line.startswith('## '):
            para = doc.add_paragraph(style='Heading 2')
            text = clean_heading_text(line[3:])
            make_run_with_font(para, text, fmt, size=fmt.get('h2-size', 14), bold=True)
            set_heading_style(para, 2)
            _apply_heading_spacing(para, fmt, 'h2')
            _clear_heading_indent(para)
        elif line.startswith('### '):
            para = doc.add_paragraph(style='Heading 3')
            text = clean_heading_text(line[4:])
            make_run_with_font(para, text, fmt, size=fmt.get('h3-size', 12), bold=True)
            set_heading_style(para, 3)
            _apply_heading_spacing(para, fmt, 'h3')
            _clear_heading_indent(para)
        elif line.startswith('#### '):
            para = doc.add_paragraph(style='Heading 4')
            text = clean_heading_text(line[5:])
            make_run_with_font(para, text, fmt, size=fmt.get('h4-size', 11), bold=True)
            set_heading_style(para, 4)
            _apply_heading_spacing(para, fmt, 'h4')
            _clear_heading_indent(para)
        elif line.strip() == '':
            i += 1
            continue
        elif re.match(r'^[-*_]{3,}$', line.strip()):
            i += 1
            continue
        else:
            # 正文段落
            para = doc.add_paragraph()
            make_run_with_font(para, line, fmt)
            # 段落格式
            pf = para.paragraph_format
            indent = fmt.get('first-line-indent', 0.74)
            if indent:
                pf.first_line_indent = Cm(indent)

        i += 1

    # 更新 Normal 样式级别的行距和首行缩进
    line_spacing = fmt.get('line-spacing', 1.5)
    try:
        normal_style = doc.styles['Normal']
        npf = normal_style.paragraph_format
        if isinstance(line_spacing, float) and line_spacing < 10:
            npf.line_spacing = line_spacing
        else:
            npf.line_spacing = Pt(line_spacing)
        # 更新 Normal 样式的首行缩进
        indent = fmt.get('first-line-indent', 0.74)
        if indent:
            npf.first_line_indent = Cm(indent)
    except:
        pass

    # 设置段落级行距（确保覆盖）
    for para in doc.paragraphs:
        pf = para.paragraph_format
        if isinstance(line_spacing, float) and line_spacing < 10:
            # 倍数行距
            pf.line_spacing = line_spacing
        else:
            # 固定磅值
            pf.line_spacing = Pt(line_spacing)

    doc.save(output_docx_path)

    # 修复文档元数据
    _fix_docx_metadata(output_docx_path)

    print(f'Word文档已生成: {output_docx_path}')
    return True


def _clear_heading_indent(para):
    """清除标题段落的首行缩进"""
    pf = para.paragraph_format
    pf.first_line_indent = None


def _apply_heading_spacing(para, fmt, level):
    """应用标题段前段后间距"""
    pf = para.paragraph_format
    before_key = f'space-before-{level}'
    after_key = f'space-after-{level}'
    if fmt.get(before_key):
        pf.space_before = Pt(fmt[before_key])
    if fmt.get(after_key):
        pf.space_after = Pt(fmt[after_key])
    # 标题不设首行缩进
    pf.first_line_indent = None


def _fix_docx_metadata(docx_path):
    """修复 docx 文档的元数据"""
    import zipfile
    from datetime import datetime, timezone

    tmp = docx_path + '.tmp'
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    with zipfile.ZipFile(docx_path, 'r') as zin:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'docProps/core.xml':
                    data = data.replace(b'2013-12-23T23:15:00Z', now_utc.encode())
                    data = data.replace(b'generated by python-docx', b'')
                    data = data.replace(b'python-docx', b'User')
                    data = data.replace(b'<cp:lastModifiedBy/>', b'<cp:lastModifiedBy>User</cp:lastModifiedBy>')
                zout.writestr(item, data)

    os.replace(tmp, docx_path)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Markdown 转 Word 技术标文档')
    parser.add_argument('input_md', help='输入 Markdown 文件路径')
    parser.add_argument('output_docx', help='输出 Word 文件路径')
    parser.add_argument('--template', '-t', help='模板 .docx 文件路径')
    parser.add_argument('--font', help='正文字体')
    parser.add_argument('--body-size', type=float, help='正文字号 (pt)')
    parser.add_argument('--line-spacing', type=float, help='行距')

    args = parser.parse_args()

    fmt_override = {}
    if args.font:
        fmt_override['font'] = args.font
        fmt_override['east_asia_font'] = args.font
    if args.body_size:
        fmt_override['body-size'] = args.body_size
    if args.line_spacing:
        fmt_override['line-spacing'] = args.line_spacing

    success = convert_md_to_word(
        args.input_md, args.output_docx,
        template_path=args.template,
        fmt_override=fmt_override if fmt_override else None
    )
    sys.exit(0 if success else 1)
