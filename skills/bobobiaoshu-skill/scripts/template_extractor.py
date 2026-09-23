#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板格式提取脚本 v1.0
从 Word 模板文件中提取所有格式参数，输出为 JSON 供 convert_to_word.py 使用

用法:
    python template_extractor.py <模板.docx> [输出.json]

如果不指定输出路径，则输出到标准输出
"""

import sys
import json
import os

def extract_template_format(template_path):
    """从 Word 模板提取格式参数"""
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(template_path)

    fmt = {
        'page': {},
        'normal': {},
        'headings': {},
        'table_style': {},
        'custom_styles': {}
    }

    # === 页面设置 ===
    for section in doc.sections:
        fmt['page'] = {
            'page_width_cm': round(section.page_width.cm, 2),
            'page_height_cm': round(section.page_height.cm, 2),
            'top_margin_cm': round(section.top_margin.cm, 2),
            'bottom_margin_cm': round(section.bottom_margin.cm, 2),
            'left_margin_cm': round(section.left_margin.cm, 2),
            'right_margin_cm': round(section.right_margin.cm, 2),
            'header_distance_cm': round(section.header_distance.cm, 2) if section.header_distance else 1.5,
            'footer_distance_cm': round(section.footer_distance.cm, 2) if section.footer_distance else 1.75,
        }
        break

    for style in doc.styles:
        if style.type is None or not style.name:
            continue

        try:
            font = style.font
            pf = style.paragraph_format
            style_info = {}
            if font.name:
                style_info['font'] = font.name
            if font.size:
                style_info['size_pt'] = font.size.pt
            if font.bold is not None:
                style_info['bold'] = font.bold
            if font.color and font.color.rgb:
                style_info['color'] = str(font.color.rgb)
            if hasattr(font, 'element'):
                rPr = font.element.find(qn('w:rPr'))
                if rPr is not None:
                    rFonts = rPr.find(qn('w:rFonts'))
                    if rFonts is not None:
                        east = rFonts.get(qn('w:eastAsia'))
                        if east:
                            style_info['east_asia_font'] = east
            if pf:
                if pf.line_spacing:
                    style_info['line_spacing'] = pf.line_spacing
                if pf.line_spacing_rule:
                    style_info['line_spacing_rule'] = str(pf.line_spacing_rule)
                if pf.space_before:
                    style_info['space_before_pt'] = pf.space_before.pt
                if pf.space_after:
                    style_info['space_after_pt'] = pf.space_after.pt
                if pf.first_line_indent:
                    style_info['first_line_indent_cm'] = round(pf.first_line_indent.cm, 2)
            if not style_info:
                continue

            name = style.name
            if name == 'Normal':
                fmt['normal'] = style_info
            elif name.startswith('Heading'):
                try:
                    level = int(name.replace('Heading ', '').replace('heading ', ''))
                    fmt['headings'][f'h{level}'] = style_info
                except ValueError:
                    pass
            elif name in ('Table Grid', '表格文字', 'Normal Table'):
                fmt['table_style'][name] = style_info
            elif name in ('正文1', 'Title', 'Plain Text', 'Footer', 'Header'):
                fmt['custom_styles'][name] = style_info
        except Exception:
            continue

    return fmt


def print_format_summary(fmt):
    """打印格式摘要"""
    print('='*60)
    print('模板格式摘要')
    print('='*60)
    p = fmt['page']
    print(f'\n[页面设置]')
    print(f'  纸张: {p["page_width_cm"]}cm x {p["page_height_cm"]}cm (A4)')
    print(f'  上/下边距: {p["top_margin_cm"]}cm / {p["bottom_margin_cm"]}cm')
    print(f'  左/右边距: {p["left_margin_cm"]}cm / {p["right_margin_cm"]}cm')
    print(f'  页眉/页脚距: {p["header_distance_cm"]}cm / {p["footer_distance_cm"]}cm')
    n = fmt['normal']
    print(f'\n[正文 Normal]')
    print(f'  字体: {n.get("font", "N/A")} | 字号: {n.get("size_pt", "N/A")}pt')
    print(f'  行距: {n.get("line_spacing", "N/A")} | 首行缩进: {n.get("first_line_indent_cm", "N/A")}cm')
    print(f'\n[标题样式]')
    for level, info in sorted(fmt['headings'].items()):
        print(f'  {level}: {info.get("font", "N/A")} {info.get("size_pt", "N/A")}pt'
              f' | 加粗: {info.get("bold", "N/A")} | 行距: {info.get("line_spacing", "N/A")} '
              f'| 段前: {info.get("space_before_pt", "N/A")}pt | 段后: {info.get("space_after_pt", "N/A")}pt')
    if fmt['table_style']:
        print(f'\n[表格样式]')
        for name, info in fmt['table_style'].items():
            print(f'  {name}: {info.get("font", "N/A")}')
    if fmt['custom_styles']:
        print(f'\n[自定义样式]')
        for name, info in fmt['custom_styles'].items():
            print(f'  {name}: {info}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python template_extractor.py <模板.docx> [输出.json]')
        sys.exit(1)
    template_path = sys.argv[1]
    if not os.path.exists(template_path):
        print(f'错误: 文件不存在: {template_path}')
        sys.exit(1)
    fmt = extract_template_format(template_path)
    print_format_summary(fmt)
    json_str = json.dumps(fmt, ensure_ascii=False, indent=2)
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f'\n格式参数已保存: {output_path}')
    else:
        print('\n--- JSON 输出 ---')
        print(json_str)
