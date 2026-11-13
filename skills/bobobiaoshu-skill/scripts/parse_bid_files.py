#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投标文件解析脚本 v4.0
三级解析策略：本地解析 → MarkItDown → 星辰 OCR API

## v4.0 重大更新（参考 Bid-Analysis-Skill 补强）
1. 表格输出格式修复：[表格] 前缀 → 标准 Markdown 管道表格（修复 eval_mapping.py 兼容性 P0-1）
2. PDF 表格提取：使用 pdfplumber.extract_tables() 提取 PDF 中的表格数据
3. 项目信息提取：自动提取项目名称、招标编号、招标人、预算金额等关键信息
4. 文档元数据提取：页数、章节数、表格数等结构化信息
5. 章节树重建：基于标题层级重建文档目录结构

## v3.0 更新
1. 整合 MarkItDown（微软开源）作为第二级解析，支持更多格式、保留结构
2. 整合星辰文档解析 API（xc-doc-parser）作为第三级，支持扫描版 PDF / 图片 OCR
3. 自动降级策略：本地解析失败 → MarkItDown → 星辰 OCR
4. 扫描版 PDF 不再只报错，自动调用 OCR 解析

## 解析优先级
1. 本地解析（pdfplumber/python-docx/openpyxl）— 快速、离线
2. MarkItDown — 结构保留更好，支持更多格式
3. 星辰 OCR API — 扫描版 PDF / 图片，高精度 OCR

## 支持格式
- .txt 纯文本
- .docx Word文档
- .pdf PDF文件（文本型/扫描版）
- .xlsx/.xls Excel表格
- .pptx PowerPoint演示文稿（MarkItDown）
- .jpg/.jpeg/.png/.bmp/.webp 图片（星辰 OCR）
- .html 网页（MarkItDown）

用法:
    python parse_bid_files.py <文件路径> [--output <输出目录>] [--level <1|2|3>]
    python parse_bid_files.py <文件路径>  # 自动选择最佳解析方式
"""

import sys
import os
import subprocess
import json
import re
from datetime import datetime

# 跨平台兼容
try:
    from macos_compat import get_python_cmd, run_subprocess
except ImportError:
    def get_python_cmd():
        return 'python'
    def run_subprocess(cmd_list, **kwargs):
        return subprocess.run(cmd_list, **kwargs)

# ============================================================
# 第一级：本地解析（原有功能）
# ============================================================

def parse_txt(file_path):
    """解析 Txt 文件"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def format_table_as_markdown(rows):
    """将表格行列表转换为 Markdown 管道表格格式

    替代旧的 [表格] 前缀格式，与 eval_mapping.py 兼容。
    """
    if not rows:
        return ''

    # 清理单元格文本
    cleaned_rows = []
    for row in rows:
        cells = [str(cell).strip().replace('\n', ' ').replace('|', '\\|') if cell else '' for cell in row]
        if any(cells):  # 至少有一个非空单元格
            cleaned_rows.append(cells)

    if not cleaned_rows:
        return ''

    # 确定列数（取最大）
    max_cols = max(len(row) for row in cleaned_rows)
    # 补齐列数
    for row in cleaned_rows:
        while len(row) < max_cols:
            row.append('')

    # 构建 Markdown 表格
    lines = []
    # 表头
    lines.append('| ' + ' | '.join(cleaned_rows[0]) + ' |')
    # 分隔行
    lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')
    # 数据行
    for row in cleaned_rows[1:]:
        lines.append('| ' + ' | '.join(row) + ' |')

    return '\n'.join(lines)


def parse_docx(file_path):
    """解析 Word 文档（v4.0: 表格输出为 Markdown 管道表格）"""
    try:
        from docx import Document
    except ImportError:
        return None  # 返回 None 表示失败，触发降级

    doc = Document(file_path)
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)

    for table in doc.tables:
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        md_table = format_table_as_markdown(rows)
        if md_table:
            paragraphs.append(md_table)

    return '\n\n'.join(paragraphs)


def check_pdf_is_scanned(file_path):
    """检测 PDF 是否为扫描版"""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) == 0:
                return True

            first_page_text = ""
            for page in pdf.pages[:3]:
                text = page.extract_text()
                if text:
                    first_page_text = text
                    break

            if not first_page_text or len(first_page_text.strip()) < 50:
                return True

            return False
    except Exception:
        return True


def parse_pdf_local(file_path):
    """本地解析 PDF（文本型）

    v4.0: 同时提取文本和表格，表格输出为 Markdown 管道表格格式。
    """
    is_scanned = check_pdf_is_scanned(file_path)

    if is_scanned:
        print("[检测] PDF 为扫描版，本地解析不适用，将尝试其他方式")
        return None

    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # 提取文本
                text = page.extract_text()
                if text:
                    text_parts.append(text)

                # v4.0: 提取表格
                try:
                    tables = page.extract_tables()
                    for table in tables:
                        if table and len(table) > 1:
                            md_table = format_table_as_markdown(table)
                            if md_table:
                                text_parts.append(md_table)
                except Exception:
                    pass  # 表格提取失败不影响文本提取

        return '\n\n'.join(text_parts)
    except ImportError:
        return None


def parse_xlsx(file_path):
    """解析 Excel 文件（v4.0: 表格输出为 Markdown 管道表格）"""
    try:
        import openpyxl
    except ImportError:
        return None

    text_parts = []
    wb = openpyxl.load_workbook(file_path, data_only=True)
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        text_parts.append(f'### Sheet: {sheet_name}\n')

        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))

        md_table = format_table_as_markdown(rows)
        if md_table:
            text_parts.append(md_table)

    return '\n\n'.join(text_parts)


def parse_local(file_path):
    """第一级：本地解析"""
    ext = os.path.splitext(file_path)[1].lower()

    parsers = {
        '.txt': parse_txt,
        '.docx': parse_docx,
        '.pdf': parse_pdf_local,
        '.xlsx': parse_xlsx,
        '.xls': parse_xlsx,
    }

    parser = parsers.get(ext)
    if not parser:
        return None

    try:
        return parser(file_path)
    except Exception as e:
        print(f"[本地解析] 失败: {e}")
        return None


# ============================================================
# 第二级：MarkItDown 解析
# ============================================================

def parse_with_markitdown(file_path):
    """第二级：使用 MarkItDown 解析

    MarkItDown 支持格式：PDF, Word, PowerPoint, Excel, Images(OCR), Audio, HTML, YouTube
    """
    try:
        # 检查 markitdown 是否安装
        py_cmd = get_python_cmd()
        result = subprocess.run(
            [py_cmd, '-c', 'import markitdown; print("ok")'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print("[MarkItDown] 未安装，跳过。安装命令: pip install 'markitdown[all]'")
            return None
    except Exception:
        print("[MarkItDown] 检查失败，跳过")
        return None

    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        if result.text_content and len(result.text_content.strip()) > 50:
            return result.text_content
        return None
    except Exception as e:
        print(f"[MarkItDown] 解析失败: {e}")
        return None


# ============================================================
# 第三级：星辰 OCR API 解析
# ============================================================

def parse_with_xc_ocr(file_path):
    """第三级：使用星辰文档解析 API

    适用于扫描版 PDF 和图片，通过 OCR 提取文字。
    依赖 xc-doc-parser 技能的 document_parser.py 脚本。
    """
    # 定位 xc-doc-parser 脚本
    possible_paths = [
        # 同级 skills 目录
        os.path.join(os.path.dirname(__file__), '..', '..', 'xc-doc-parser', 'scripts', 'document_parser.py'),
        # TeleAgent skills 目录
        os.path.join(os.environ.get('TELEAGENT_CONFIG_DIR', ''), 'skills', 'xc-doc-parser', 'scripts', 'document_parser.py'),
        # 默认路径
        os.path.expanduser('~/.config/TeleAgent/skills/xc-doc-parser/scripts/document_parser.py'),
    ]

    parser_script = None
    for p in possible_paths:
        p = os.path.normpath(p)
        if os.path.exists(p):
            parser_script = p
            break

    if not parser_script:
        print("[星辰OCR] 未找到 xc-doc-parser 脚本，跳过")
        return None

    # 支持的格式
    ext = os.path.splitext(file_path)[1].lower()
    supported = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    if ext not in supported:
        print(f"[星辰OCR] 不支持格式: {ext}，跳过")
        return None

    # 文件大小检查（10MB 限制）
    if os.path.exists(file_path) and os.path.getsize(file_path) > 10 * 1024 * 1024:
        print("[星辰OCR] 文件超过 10MB 限制，跳过")
        return None

    try:
        output_dir = os.path.dirname(file_path) or '.'
        py_cmd = get_python_cmd()
        result = subprocess.run(
            [py_cmd, parser_script, file_path, '--format', 'markdown', '-o', output_dir],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            print(f"[星辰OCR] 解析失败: {result.stderr[:200]}")
            return None

        # 查找输出文件
        basename = os.path.splitext(os.path.basename(file_path))[0]
        output_md = os.path.join(output_dir, f'{basename}_解析结果.md')

        if os.path.exists(output_md):
            with open(output_md, 'r', encoding='utf-8') as f:
                content = f.read()
            if content.strip():
                return content

        # 如果没有找到文件，检查 stdout
        if result.stdout and len(result.stdout.strip()) > 50:
            return result.stdout

        return None
    except subprocess.TimeoutExpired:
        print("[星辰OCR] 解析超时（300秒）")
        return None
    except Exception as e:
        print(f"[星辰OCR] 异常: {e}")
        return None


# ============================================================
# v4.0 新增：项目信息提取
# ============================================================

def extract_project_info(content):
    """从解析后的文档内容中提取项目关键信息

    参考 Bid-Analysis-Skill 的信息提取模块，使用正则+关键词模式匹配。
    返回 JSON 格式的结构化信息。
    """
    info = {
        'project_name': None,
        'project_code': None,
        'tender_org': None,       # 招标人
        'budget_amount': None,    # 预算金额
        'bid_deadline': None,     # 投标截止时间
        'open_bid_time': None,    # 开标时间
        'total_score': None,      # 总分
        'duration_days': None,    # 服务期限
    }

    lines = content.split('\n')
    full_text = content

    # 项目名称
    name_patterns = [
        r'项目名称[：:]\s*(.+?)(?:\n|$)',
        r'项目名称[：:　\s]*(.+?)(?:\n|$)',
        r'工程名称[：:]\s*(.+?)(?:\n|$)',
        r'采购项目[：:]\s*(.+?)(?:\n|$)',
    ]
    for pat in name_patterns:
        m = re.search(pat, full_text)
        if m:
            info['project_name'] = m.group(1).strip()[:100]
            break

    # 项目编号
    code_patterns = [
        r'项目编号[：:]\s*([A-Za-z0-9\-\u4e00-\u9fff]+)',
        r'招标编号[：:]\s*([A-Za-z0-9\-\u4e00-\u9fff]+)',
        r'采购编号[：:]\s*([A-Za-z0-9\-\u4e00-\u9fff]+)',
        r'标段编号[：:]\s*([A-Za-z0-9\-\u4e00-\u9fff]+)',
    ]
    for pat in code_patterns:
        m = re.search(pat, full_text)
        if m:
            code = m.group(1).strip()
            # 过滤掉明显过长的垃圾文本
            if len(code) < 50 and not code.startswith('（'):
                info['project_code'] = code
                break

    # 招标人
    org_patterns = [
        r'招标人[：:]\s*(.+?)(?:\n|$)',
        r'采购人[：:]\s*(.+?)(?:\n|$)',
        r'甲方[：:]\s*(.+?)(?:\n|$)',
    ]
    for pat in org_patterns:
        m = re.search(pat, full_text)
        if m:
            org = m.group(1).strip()[:80]
            if len(org) < 50:
                info['tender_org'] = org
                break

    # 预算金额
    budget_patterns = [
        r'预算[金额]?[：:]\s*([\d,.]+\s*[万 亿元]*)',
        r'最高限价[：:]\s*([\d,.]+\s*[万 亿元]*)',
        r'预算总价[：:]\s*([\d,.]+\s*[万 亿元]*)',
    ]
    for pat in budget_patterns:
        m = re.search(pat, full_text)
        if m:
            info['budget_amount'] = m.group(1).strip()[:30]
            break

    # 投标截止时间
    deadline_patterns = [
        r'投标截止[时间]?[：:]\s*(.+?)(?:\n|$)',
        r'响应文件提交截止[时间]?[：:]\s*(.+?)(?:\n|$)',
        r'递交截止[时间]?[：:]\s*(.+?)(?:\n|$)',
    ]
    for pat in deadline_patterns:
        m = re.search(pat, full_text)
        if m:
            info['bid_deadline'] = m.group(1).strip()[:50]
            break

    # 开标时间
    open_patterns = [
        r'开标时间[：:]\s*(.+?)(?:\n|$)',
        r'开启时间[：:]\s*(.+?)(?:\n|$)',
    ]
    for pat in open_patterns:
        m = re.search(pat, full_text)
        if m:
            info['open_bid_time'] = m.group(1).strip()[:50]
            break

    # 总分
    score_patterns = [
        r'满分[为共]?\s*(\d+)\s*分',
        r'总分[为共]?\s*(\d+)\s*分',
        r'合计[为共]?\s*(\d+)\s*分',
        r'评分总[分值][为共]?\s*(\d+)\s*分',
        r'=\s*(\d+)\s*分',
    ]
    for pat in score_patterns:
        m = re.search(pat, full_text)
        if m:
            score = int(m.group(1))
            if 50 <= score <= 200:  # 合理的总分范围
                info['total_score'] = score
                break

    # 服务期限
    duration_patterns = [
        r'服务期[：:]\s*(\d+)\s*[个月天年]',
        r'合同期限[：:]\s*(\d+)\s*[个月天年]',
        r'工期[：:]\s*(\d+)\s*[天日月]',
    ]
    for pat in duration_patterns:
        m = re.search(pat, full_text)
        if m:
            info['duration_days'] = m.group(0).strip()[:30]
            break

    return info


def extract_metadata(file_path, content, method):
    """提取文档元数据

    参考 Bid-Analysis-Skill 的元数据提取功能。
    """
    meta = {
        'file_name': os.path.basename(file_path),
        'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
        'parse_method': method,
        'parse_time': datetime.now().isoformat(),
        'page_count': None,
        'char_count': len(content) if content else 0,
        'table_count': 0,
        'heading_count': 0,
    }

    # 统计表格数（Markdown 管道表格）
    if content:
        meta['table_count'] = content.count('| --- |') + content.count('|---|')
        # 统计标题数
        meta['heading_count'] = len(re.findall(r'^#{1,6}\s+', content, re.MULTILINE))

    # PDF 页数
    if file_path.lower().endswith('.pdf'):
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                meta['page_count'] = len(pdf.pages)
        except Exception:
            pass

    # DOCX 页数（近似）
    elif file_path.lower().endswith('.docx'):
        try:
            from docx import Document
            doc = Document(file_path)
            # 近似估算：每页约 500 字
            total_chars = sum(len(p.text) for p in doc.paragraphs)
            meta['page_count'] = max(1, total_chars // 500)
        except Exception:
            pass

    return meta


# ============================================================
# 统一解析入口
# ============================================================

def parse_file(file_path, max_level=3):
    """三级解析策略：自动降级

    Args:
        file_path: 文件路径
        max_level: 最大解析级别 (1=仅本地, 2=本地+MarkItDown, 3=全部)
    Returns:
        (content, method) 元素组：解析内容和使用的解析方法
    """
    if not os.path.exists(file_path):
        return f"[错误] 文件不存在: {file_path}", None

    ext = os.path.splitext(file_path)[1].lower()
    all_supported = {'.txt', '.docx', '.pdf', '.xlsx', '.xls', '.pptx',
                     '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.html'}

    if ext not in all_supported:
        return f"[错误] 不支持的格式: {ext}\n支持: {', '.join(sorted(all_supported))}", None

    # 图片文件直接跳到 OCR
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
    if ext in image_exts:
        print("[策略] 图片文件，使用星辰 OCR 解析")
        content = parse_with_xc_ocr(file_path) if max_level >= 3 else None
        if content:
            return content, 'xc-ocr'
        return "[错误] 图片解析失败，请检查 xc-doc-parser 是否配置正确", None

    # 第一级：本地解析
    print("[解析] 第一级：本地解析...")
    content = parse_local(file_path)
    if content and len(content.strip()) > 50:
        print(f"[解析] 本地解析成功 ({len(content)} 字符)")
        return content, 'local'

    # 第二级：MarkItDown
    if max_level >= 2:
        print("[解析] 第一级不足，尝试第二级：MarkItDown...")
        content = parse_with_markitdown(file_path)
        if content and len(content.strip()) > 50:
            print(f"[解析] MarkItDown 解析成功 ({len(content)} 字符)")
            return content, 'markitdown'

    # 第三级：星辰 OCR
    if max_level >= 3:
        print("[解析] 前两级不足，尝试第三级：星辰 OCR...")
        content = parse_with_xc_ocr(file_path)
        if content and len(content.strip()) > 50:
            print(f"[解析] 星辰 OCR 解析成功 ({len(content)} 字符)")
            return content, 'xc-ocr'

    return "[错误] 所有解析方式均失败，请检查文件是否损坏或手动提取内容", None


def main():
    if len(sys.argv) < 2:
        print('用法: python parse_bid_files.py <文件路径> [--output <输出目录>] [--level <1|2|3>]')
        print('')
        print('解析策略（自动降级）:')
        print('  第一级: 本地解析 (pdfplumber/python-docx/openpyxl)')
        print('  第二级: MarkItDown (微软开源，结构保留更好)')
        print('  第三级: 星辰 OCR API (扫描版PDF/图片，高精度OCR)')
        print('')
        print('支持格式: txt, docx, pdf, xlsx, xls, pptx, jpg, png, bmp, webp, html')
        sys.exit(1)

    file_path = sys.argv[1]
    output_dir = None
    max_level = 3

    # 解析参数
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif args[i] == '--level' and i + 1 < len(args):
            max_level = int(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"正在解析: {file_path}")
    print(f"解析级别: {max_level} (1=本地, 2=+MarkItDown, 3=+星辰OCR)")
    print("-" * 60)

    content, method = parse_file(file_path, max_level)

    print("-" * 60)
    print(f"解析方法: {method or '失败'}")
    print()

    # 输出到文件
    if output_dir and content and not content.startswith('[错误]'):
        os.makedirs(output_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(output_dir, f'{basename}_解析结果.md')

        # v4.0: 在内容头部添加元数据和项目信息
        meta = extract_metadata(file_path, content, method)
        project_info = extract_project_info(content)

        header = f"""<!-- 文档元数据
{json.dumps(meta, ensure_ascii=False, indent=2)}
-->

<!-- 项目信息
{json.dumps(project_info, ensure_ascii=False, indent=2)}
-->

"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header + content)
        print(f"解析结果已保存: {output_path}")

        # v4.0: 同时保存项目信息 JSON
        info_path = os.path.join(output_dir, f'{basename}_项目信息.json')
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump({'metadata': meta, 'project_info': project_info}, f, ensure_ascii=False, indent=2)
        print(f"项目信息已保存: {info_path}")
    else:
        print(content)

        # v4.0: 即使不保存文件也输出项目信息
        if content and not content.startswith('[错误]'):
            project_info = extract_project_info(content)
            if any(project_info.values()):
                print("\n--- 提取到的项目信息 ---")
                for k, v in project_info.items():
                    if v:
                        print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
