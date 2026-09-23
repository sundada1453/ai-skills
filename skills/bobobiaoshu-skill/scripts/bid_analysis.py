#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标书分析报告生成器 v1.0
参考 GitHub Bid-Analysis-Skill (aidevsource/Bid-Analysis-Skill) 设计

功能：
  从 parse_bid_files.py 解析结果中提取关键信息，生成结构化分析报告。
  报告包含：基本信息、时间节点、评分标准、投标重点、风险提示等 10 个章节。

与 eval_mapping.py 的区别：
  - eval_mapping.py 专注评分点→章节映射，用于编写阶段
  - bid_analysis.py 专注招标文件全局分析，用于编写前的决策支持

用法:
  python bid_analysis.py <解析结果.md> [--output <报告目录>]
  python bid_analysis.py <解析结果.md> --info <项目信息.json> --output <报告目录>
"""

import sys
import os
import re
import json
from datetime import datetime
from collections import Counter


def extract_scoring_criteria(content):
    """提取评分标准

    支持两种格式：
    1. Markdown 管道表格（v4.0 格式）
    2. [表格] 前缀格式（旧格式兼容）
    """
    criteria = []
    lines = content.split('\n')

    # 策略1: 解析 Markdown 管道表格
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 检测表头行（包含"评分"或"分值"或"评审"等关键词）
        if line.startswith('|') and any(kw in line for kw in ['评分', '分值', '评审', '打分', '评分因素', '评分项目']):
            # 读取完整表格
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1

            if len(table_lines) >= 2:
                # 解析表格
                rows = []
                for tl in table_lines:
                    cells = [c.strip() for c in tl.split('|')[1:-1]]
                    rows.append(cells)

                # 跳过分隔行
                data_rows = [r for r in rows if not all(c.replace('-', '').strip() == '' for c in r)]

                if len(data_rows) >= 2:
                    header = data_rows[0]
                    for row in data_rows[1:]:
                        item = {}
                        for j, cell in enumerate(row):
                            if j < len(header):
                                item[header[j]] = cell
                        # 提取分值
                        for v in item.values():
                            score_match = re.search(r'(\d+)\s*分', str(v))
                            if score_match:
                                item['_score'] = int(score_match.group(1))
                                break
                        criteria.append(item)
            continue
        i += 1

    # 策略2: 搜索"评分标准"附近的内容
    if not criteria:
        scoring_section = re.search(
            r'评分[标准因素].*?(?=\n#{1,3}\s|\n\s*\n\s*\n|\Z)',
            content, re.DOTALL
        )
        if scoring_section:
            section_text = scoring_section.group(0)
            # 提取带分值的条目
            items = re.findall(r'(.+?)\s+(\d+)\s*分', section_text)
            for text, score in items:
                if len(text) > 2 and len(text) < 200:
                    criteria.append({
                        '内容': text.strip(),
                        '_score': int(score),
                    })

    return criteria


def extract_key_info(content):
    """提取关键信息摘要"""
    info = {}

    # 项目名称
    m = re.search(r'项目名称[：:]\s*(.+?)(?:\n|$)', content)
    if m:
        info['project_name'] = m.group(1).strip()[:100]

    # 项目编号
    m = re.search(r'(?:项目|招标|采购)编号[：:]\s*([A-Za-z0-9\-\u4e00-\u9fff]+)', content)
    if m and len(m.group(1).strip()) < 50:
        info['project_code'] = m.group(1).strip()

    # 招标人
    m = re.search(r'(?:招标人|采购人)[：:]\s*(.+?)(?:\n|$)', content)
    if m:
        info['tender_org'] = m.group(1).strip()[:80]

    # 预算金额
    m = re.search(r'(?:预算[金额]?|最高限价)[：:]\s*([\d,.]+\s*[万 亿元]*)', content)
    if m:
        info['budget'] = m.group(1).strip()

    # 投标截止时间
    m = re.search(r'(?:投标截止|响应文件提交截止)[时间]?[：:]\s*(.+?)(?:\n|$)', content)
    if m:
        info['bid_deadline'] = m.group(1).strip()[:50]

    # 开标时间
    m = re.search(r'(?:开标|开启)时间[：:]\s*(.+?)(?:\n|$)', content)
    if m:
        info['open_bid_time'] = m.group(1).strip()[:50]

    # 服务期限
    m = re.search(r'(?:服务期|合同期限|工期)[：:]\s*(.+?)(?:\n|$)', content)
    if m:
        info['duration'] = m.group(1).strip()[:50]

    # 总分
    for pat in [r'满分[为共]?\s*(\d+)\s*分', r'总分[为共]?\s*(\d+)\s*分', r'=\s*(\d+)\s*分']:
        m = re.search(pat, content)
        if m:
            score = int(m.group(1))
            if 50 <= score <= 200:
                info['total_score'] = score
                break

    return info


def extract_time_nodes(content):
    """提取时间节点"""
    nodes = []
    time_patterns = [
        (r'投标截止[时间]?[：:]\s*(.+?)(?:\n|$)', '投标截止时间'),
        (r'开标时间[：:]\s*(.+?)(?:\n|$)', '开标时间'),
        (r'答疑[截止]?时间[：:]\s*(.+?)(?:\n|$)', '答疑截止时间'),
        (r'合同签订[期限]?[：:]\s*(.+?)(?:\n|$)', '合同签订期限'),
        (r'服务期[：:]\s*(.+?)(?:\n|$)', '服务期限'),
        (r'投标有效期[：:]\s*(.+?)(?:\n|$)', '投标有效期'),
        (r'公示期[：:]\s*(.+?)(?:\n|$)', '公示期'),
    ]

    for pat, label in time_patterns:
        m = re.search(pat, content)
        if m:
            nodes.append({'节点': label, '时间': m.group(1).strip()[:80]})

    return nodes


def extract_risk_items(content):
    """提取风险相关条款"""
    risks = []
    risk_keywords = [
        ('无效投标', '高风险', r'无效投标.*?(?:\n|$)'),
        ('废标', '高风险', r'废标.*?(?:\n|$)'),
        ('否决', '高风险', r'(?:否决|拒绝)投标.*?(?:\n|$)'),
        ('围标串标', '高风险', r'围标.*?串标.*?(?:\n|$)'),
        ('违约责任', '中风险', r'违约责任.*?(?:\n|$)'),
        ('知识产权', '中风险', r'知识产权.*?(?:\n|$)'),
        ('保密', '中风险', r'保密[要求条款].*?(?:\n|$)'),
        ('罚款', '中风险', r'罚款.*?(?:\n|$)'),
    ]

    for label, level, pat in risk_keywords:
        matches = re.findall(pat, content, re.IGNORECASE)
        for match in matches[:3]:  # 每类最多取3条
            text = match.strip()[:200]
            if len(text) > 10:
                risks.append({'风险类型': label, '风险等级': level, '条款摘要': text})

    return risks


def extract_special_terms(content):
    """提取需特别关注的条款"""
    special = []
    special_patterns = [
        ('实质性要求', r'★.*?(?:\n|$)'),
        ('星号条款', r'\*.*?实质性.*?(?:\n|$)'),
        ('强制性要求', r'强制[性要求].*?(?:\n|$)'),
        ('必备条件', r'必须具备.*?(?:\n|$)'),
    ]

    for label, pat in special_patterns:
        matches = re.findall(pat, content)
        for match in matches[:5]:
            text = match.strip()[:200]
            if len(text) > 5:
                special.append({'类型': label, '条款摘要': text})

    return special


def extract_tech_requirements(content):
    """提取技术需求/采购需求"""
    tech_section = re.search(
        r'(?:技术[要求规格]|采购需求|第五章).*?(?=\n#{1,3}\s[第六七八九]|\Z)',
        content, re.DOTALL
    )
    if tech_section:
        section_text = tech_section.group(0)
        # 提取技术参数条目
        items = re.findall(
            r'(?:^|\n)\s*(?:\d+[.、）]\s*)(.+?)(?=\n\s*\d+[.、）]|\Z)',
            section_text
        )
        return [item.strip()[:200] for item in items[:20] if len(item.strip()) > 5]
    return []


def generate_report(content, project_info=None):
    """生成完整分析报告"""

    if project_info is None:
        project_info = extract_key_info(content)

    time_nodes = extract_time_nodes(content)
    scoring = extract_scoring_criteria(content)
    risks = extract_risk_items(content)
    special = extract_special_terms(content)
    tech_reqs = extract_tech_requirements(content)

    # 计算评分分布
    score_distribution = {}
    if scoring:
        for item in scoring:
            score = item.get('_score', 0)
            if score:
                # 提取评分因素名
                name = ''
                for k, v in item.items():
                    if k != '_score' and v and '评分' in str(k):
                        name = str(v).strip()[:30]
                        break
                if not name:
                    for k, v in item.items():
                        if k != '_score' and v:
                            name = str(v).strip()[:30]
                            break
                score_distribution[name] = score

    total_score = project_info.get('total_score', sum(score_distribution.values()))

    # 评分重点排序（按分值降序）
    sorted_scoring = sorted(score_distribution.items(), key=lambda x: -x[1])

    report = f"""# {project_info.get('project_name', '未知项目')} 标书分析报告

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 分析工具：bobobiaoshu-skill v9.0 bid_analysis.py

---

## 一、基本信息摘要

| 信息项 | 内容 |
|--------|------|
| 项目名称 | {project_info.get('project_name', '未提取到')} |
| 项目编号 | {project_info.get('project_code', '未提取到')} |
| 招标人 | {project_info.get('tender_org', '未提取到')} |
| 预算金额 | {project_info.get('budget', '未提取到')} |
| 服务期限 | {project_info.get('duration', '未提取到')} |
| 总分 | {total_score or '未提取到'} |

## 二、时间节点梳理

"""
    if time_nodes:
        report += "| 节点 | 时间/期限 |\n|------|-----------|\n"
        for node in time_nodes:
            report += f"| {node['节点']} | {node['时间']} |\n"
    else:
        report += "未提取到时间节点信息。\n"

    report += f"""
## 三、采购需求与技术规格

"""
    if tech_reqs:
        report += "提取到以下技术需求条目：\n\n"
        for i, req in enumerate(tech_reqs[:15], 1):
            report += f"{i}. {req}\n"
    else:
        report += "未提取到明确的技术需求条目，建议人工查阅招标文件第五章技术规范书。\n"

    report += f"""
## 四、评分标准深度解析

"""
    if sorted_scoring:
        report += "| 序号 | 评分因素 | 分值 | 占比 |\n|------|---------|------|------|\n"
        for i, (name, score) in enumerate(sorted_scoring, 1):
            pct = f"{score/total_score*100:.1f}%" if total_score else "—"
            report += f"| {i} | {name} | {score} | {pct} |\n"
        report += f"\n**评分项总数**: {len(sorted_scoring)}  \n"
        report += f"**总分**: {total_score}\n"
    else:
        report += "未自动提取到评分标准表格。建议使用 `--scoring` 参数手动提供评分标准文件。\n"

    report += f"""
## 五、商务条款与投标要求

建议人工查阅以下条款：
- 付款方式及条件
- 资格要求（资质等级、人员要求、业绩要求）
- 实质性要求（★ 标记条款）
- 验收标准
- 知识产权条款

## 六、投标重点分析

"""
    if sorted_scoring:
        top_items = sorted_scoring[:5]
        report += "按分值排序的投标重点领域：\n\n"
        for i, (name, score) in enumerate(top_items, 1):
            pct = f"{score/total_score*100:.1f}%" if total_score else "—"
            report += f"{i}. **{name}**（{score}分，占比{pct}）— 这是高分项，需重点编写，分配更多字数和更详细的技术方案\n"
    else:
        report += "需先提取评分标准才能分析投标重点。\n"

    report += f"""
## 七、技术难点分析

建议根据招标文件中的技术要求，重点关注：
- 技术方案的创新性和可行性
- 项目团队的人员配置与资质
- 实施进度安排的合理性
- 质量保障措施的完整性
- 售后服务方案的具体性

## 八、潜在风险提示

"""
    if risks:
        report += "| 风险等级 | 风险类型 | 条款摘要 |\n|---------|---------|----------|\n"
        # 按风险等级排序
        level_order = {'高风险': 0, '中风险': 1, '低风险': 2}
        sorted_risks = sorted(risks, key=lambda x: level_order.get(x['风险等级'], 3))
        for risk in sorted_risks:
            emoji = {'高风险': '🔴', '中风险': '🟡', '低风险': '🟢'}.get(risk['风险等级'], '⚪')
            report += f"| {emoji} {risk['风险等级']} | {risk['风险类型']} | {risk['条款摘要'][:60]} |\n"
    else:
        report += "未自动提取到风险条款。建议人工检查招标文件中的以下内容：\n"
        report += "- 无效投标情形\n- 废标条款\n- 违约责任\n- 知识产权要求\n"

    report += f"""
## 九、需特别关注的条款

"""
    if special:
        for item in special:
            report += f"- **{item['类型']}**: {item['条款摘要'][:80]}\n"
    else:
        report += "未自动提取到特别条款。建议人工检查：\n"
        report += "- ★ 标记的实质性要求\n- 强制性技术参数\n- 必备资质条件\n"

    report += f"""
## 十、综合竞争态势分析

### 评分权重一览

"""
    if sorted_scoring:
        # 分类统计
        categories = {}
        for name, score in sorted_scoring:
            if any(kw in name for kw in ['价格', '报价', '下浮']):
                cat = '价格分'
            elif any(kw in name for kw in ['商务', '资质', '业绩', '财务']):
                cat = '商务分'
            elif any(kw in name for kw in ['技术', '方案', '服务', '实施']):
                cat = '技术分'
            else:
                cat = '其他'
            categories[cat] = categories.get(cat, 0) + score

        report += "| 类别 | 分值 | 占比 |\n|------|------|------|\n"
        for cat, score in sorted(categories.items(), key=lambda x: -x[1]):
            pct = f"{score/total_score*100:.1f}%" if total_score else "—"
            report += f"| {cat} | {score} | {pct} |\n"
    else:
        report += "需先提取评分标准才能分析竞争态势。\n"

    report += f"""
### 核心结论

- **项目名称**: {project_info.get('project_name', '未知')}
- **总分**: {total_score or '未知'}
- **评分项数**: {len(sorted_scoring)}
- **风险条款数**: {len(risks)}
- **特别条款数**: {len(special)}

### 投标准备建议

1. **高分项优先**: 优先准备高分评分项的技术方案内容
2. **风险规避**: 逐条核对风险条款，确保标书不触犯无效投标情形
3. **实质要求**: 确保所有★标记的实质性要求全部响应
4. **字数分配**: 使用 eval_mapping.py 自动生成字数分配表，按分值分配编写字数

---

*本报告由 bobobiaoshu-skill bid_analysis.py v1.0 自动生成*
*参考: [Bid-Analysis-Skill](https://github.com/aidevsource/Bid-Analysis-Skill)*
"""

    return report


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = None
    info_file = None

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif args[i] == '--info' and i + 1 < len(args):
            info_file = args[i + 1]
            i += 2
        else:
            i += 1

    if not os.path.exists(input_file):
        print(f"错误: 文件不存在: {input_file}")
        sys.exit(1)

    # 读取解析结果
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 读取项目信息（如果提供）
    project_info = None
    if info_file and os.path.exists(info_file):
        with open(info_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            project_info = data.get('project_info', data)

    # 生成报告
    print("正在生成分析报告...")
    report = generate_report(content, project_info)

    # 输出
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        basename = os.path.splitext(os.path.basename(input_file))[0]
        output_path = os.path.join(output_dir, f'{basename}_标书分析报告.md')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"分析报告已保存: {output_path}")
    else:
        print(report)


if __name__ == '__main__':
    main()
