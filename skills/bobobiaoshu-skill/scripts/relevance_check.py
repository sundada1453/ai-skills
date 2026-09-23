#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容相关性检查器 v1.0
检查片段改写后的内容与当前招标项目的实质相关性，确保片段不仅字眼替换了，
内容本身也与项目需求高度相关。

核心逻辑：
  1. 从招标文件解析结果中提取项目核心关键词（技术要求、业务场景、系统功能等）
  2. 从改写后的片段中提取内容主题关键词
  3. 比对两者关键词重合度，计算相关性评分
  4. 检测片段中是否有大量与项目无关的领域概念（跨领域污染）
  5. 输出相关性评分：高（可直接用）/中（需大幅改写）/低（建议弃用）

用法:
  python relevance_check.py check <改写后的片段.md> --tender <招标文件解析结果.md> [--project <项目名>]
  python relevance_check.py check <改写后的片段.md> --tender-dir <招标文件解析目录> [--project <项目名>]
  python relevance_check.py score <改写后的片段.md> --tender <招标文件解析结果.md>

示例:
  # 检查改写后的片段与招标文件的相关性
  python relevance_check.py check adapted_snippet.md --tender 招标文件_解析结果.md --project "漏洞管理平台运营"

  # 批量检查目录下所有改写后的片段
  python relevance_check.py check-dir <片段目录> --tender 招标文件_解析结果.md --project "漏洞管理平台运营"
"""

import sys
import os
import re
import json
from collections import Counter
from pathlib import Path

# ============================================================
# 领域关键词库（按项目类型分类）
# ============================================================

# 电信运维类项目关键词
DOMAIN_TELECOM_OPS = {
    "DPI", "信令", "巡检", "机房", "分光器", "采集", "合成", "分流器",
    "网络流量", "光功率", "光纤", "基站", "核心网", "承载网", "传输网",
    "故障处理", "故障分级", "应急通信", "重要通信保障", "备件",
    "网络设备", "路由器", "交换机", "防火墙",
}

# 安全运营类项目关键词
DOMAIN_SECURITY_OPS = {
    "漏洞", "补丁", "基线", "弱口令", "渗透", "等保", "安全审计",
    "安全事件", "安全运营", "SOC", "SIEM", "威胁情报", "入侵检测",
    "WAF", "APT", "DDoS", "应急响应", "安全加固", "安全检查",
    "风险评估", "脆弱性", "资产", "边界", "态势感知",
}

# 软件开发类项目关键词
DOMAIN_SOFTWARE_DEV = {
    "微服务", "容器", "Docker", "Kubernetes", "CI/CD", "敏捷开发",
    "前后端分离", "API", "数据库", "缓存", "消息队列", "中间件",
    "前端", "后端", "框架", "Spring", "Vue", "React",
    "需求分析", "概要设计", "详细设计", "编码", "单元测试", "集成测试",
    "版本管理", "Git", "Maven", "构建", "部署",
}

# 数据安全类项目关键词
DOMAIN_DATA_SECURITY = {
    "数据分类分级", "数据脱敏", "数据加密", "数据防泄漏", "DLP",
    "隐私保护", "个人信息", "数据生命周期", "数据出境",
    "密评", "密码", "国密", "KMS", "密钥管理",
    "数据治理", "数据资产", "数据目录", "数据血缘",
}

# 运维保障类项目关键词
DOMAIN_IT_OPS = {
    "巡检", "监控", "告警", "故障", "应急", "预案",
    "驻场", "SLA", "响应时间", "恢复时间", "可用性",
    "备份", "容灾", "演练", "运维平台", "CMDB",
    "工单", "变更", "发布", "配置管理", "知识库",
}

# 项目管理类关键词（通用，不算跨领域）
DOMAIN_PROJECT_MGMT = {
    "进度", "里程碑", "质量", "风险", "团队", "沟通",
    "计划", "验收", "收尾", "启动", "变更", "文档",
    "WBS", "甘特图", "关键路径", "资源", "成本",
}

ALL_DOMAINS = {
    "电信运维": DOMAIN_TELECOM_OPS,
    "安全运营": DOMAIN_SECURITY_OPS,
    "软件开发": DOMAIN_SOFTWARE_DEV,
    "数据安全": DOMAIN_DATA_SECURITY,
    "运维保障": DOMAIN_IT_OPS,
}


def extract_keywords_from_tender(tender_content):
    """从招标文件解析结果中提取项目核心关键词

    Args:
        tender_content: 招标文件解析结果的文本内容

    Returns:
        set of keywords
    """
    keywords = set()

    # 1. 匹配所有领域关键词
    for domain, domain_kws in ALL_DOMAINS.items():
        for kw in domain_kws:
            if kw.lower() in tender_content.lower():
                keywords.add(kw)

    # 2. 提取技术名词（大写英文缩写，2-8字母）
    abbrevs = re.findall(r'\b[A-Z]{2,8}\b', tender_content)
    # 过滤掉常见的非技术缩写
    stop_abbrevs = {"PDF", "DOC", "XLS", "PPT", "URL", "HTTP", "HTTPS", "DNA", "RGB", "VIP", "CEO", "CFO", "IT"}
    for ab in abbrevs:
        if ab not in stop_abbrevs and len(ab) >= 2:
            keywords.add(ab)

    # 3. 提取高频名词短语（中文，2-6字，出现3次以上）
    # 简单方法：提取所有中文词组
    cn_words = re.findall(r'[\u4e00-\u9fa5]{2,8}', tender_content)
    word_freq = Counter(cn_words)
    for word, freq in word_freq.items():
        if freq >= 3 and len(word) >= 2:
            # 过滤掉通用词
            if word not in {"我们", "乙方", "甲方", "项目", "方案", "实施", "管理", "服务",
                          "系统", "平台", "建设", "要求", "包括", "以及", "对于", "通过",
                          "进行", "需要", "可以", "能够", "提供", "支持", "确保", "保证",
                          "满足", "达到", "实现", "基于", "根据", "按照", "依据", "参照",
                          "结合", "针对", "围绕", "聚焦", "立足", "凭借",
                          "本项目", "招标人", "投标人", "供应商", "采购人"}:
                keywords.add(word)

    return keywords


def extract_keywords_from_snippet(snippet_content):
    """从片段内容中提取关键词

    Args:
        snippet_content: 片段文本内容

    Returns:
        set of keywords
    """
    keywords = set()

    # 1. 匹配所有领域关键词
    for domain, domain_kws in ALL_DOMAINS.items():
        for kw in domain_kws:
            if kw.lower() in snippet_content.lower():
                keywords.add(kw)

    # 2. 提取技术名词
    abbrevs = re.findall(r'\b[A-Z]{2,8}\b', snippet_content)
    stop_abbrevs = {"PDF", "DOC", "XLS", "PPT", "URL", "HTTP", "HTTPS", "DNA", "RGB", "VIP", "CEO", "CFO", "IT"}
    for ab in abbrevs:
        if ab not in stop_abbrevs and len(ab) >= 2:
            keywords.add(ab)

    # 3. 提取高频中文词组
    cn_words = re.findall(r'[\u4e00-\u9fa5]{2,8}', snippet_content)
    word_freq = Counter(cn_words)
    for word, freq in word_freq.items():
        if freq >= 2 and len(word) >= 2:
            if word not in {"我们", "乙方", "甲方", "项目", "方案", "实施", "管理", "服务",
                          "系统", "平台", "建设", "要求", "包括", "以及", "对于", "通过",
                          "进行", "需要", "可以", "能够", "提供", "支持", "确保", "保证",
                          "满足", "达到", "实现", "基于", "根据", "按照", "依据", "参照",
                          "结合", "针对", "围绕", "聚焦", "立足", "凭借",
                          "本项目", "招标人", "投标人", "供应商", "采购人"}:
                keywords.add(word)

    return keywords


def detect_domain_contamination(snippet_content, tender_keywords):
    """检测片段中的跨领域污染

    检查片段中是否包含大量与招标项目无关的领域概念。

    Args:
        snippet_content: 片段文本
        tender_keywords: 招标文件关键词集合

    Returns:
        list of (领域, 污染词列表, 污染程度)
    """
    contamination = []

    for domain, domain_kws in ALL_DOMAINS.items():
        # 该领域在片段中出现的词
        snippet_domain_words = [kw for kw in domain_kws if kw.lower() in snippet_content.lower()]
        # 该领域在招标文件中出现的词
        tender_domain_words = [kw for kw in domain_kws if kw in tender_keywords]

        # 如果片段中大量出现某领域词，但招标文件中几乎没有 → 跨领域污染
        if len(snippet_domain_words) >= 3 and len(tender_domain_words) == 0:
            severity = "严重" if len(snippet_domain_words) >= 5 else "中等"
            contamination.append((domain, snippet_domain_words, severity))
        elif len(snippet_domain_words) >= 5 and len(tender_domain_words) <= 1:
            severity = "中等" if len(snippet_domain_words) >= 8 else "轻微"
            contamination.append((domain, snippet_domain_words, severity))

    return contamination


def calculate_relevance(tender_keywords, snippet_keywords, snippet_content, tender_content):
    """计算相关性评分

    Returns:
        (score, level, details)
        score: 0-100
        level: "高" / "中" / "低"
        details: dict with breakdown
    """
    if not tender_keywords or not snippet_keywords:
        return 0, "低", {"reason": "无法提取关键词"}

    overlap = tender_keywords & snippet_keywords

    # 1. 片段关键词中相关占比（最重要——片段中有多少关键词与招标项目相关）
    snippet_relevance_ratio = len(overlap) / max(len(snippet_keywords), 1)

    # 2. 核心业务词匹配（招标文件中出现>=5次的高频词，权重更高）
    # 重新从招标文件中统计词频，提取核心关键词
    cn_words = re.findall(r'[\u4e00-\u9fa5]{2,8}', tender_content)
    tender_word_freq = Counter(cn_words)
    core_tender_keywords = set()
    for word, freq in tender_word_freq.items():
        if freq >= 5 and word in tender_keywords:
            core_tender_keywords.add(word)
    # 领域关键词也算核心词
    for domain_kws in ALL_DOMAINS.values():
        for kw in domain_kws:
            if kw in tender_keywords:
                core_tender_keywords.add(kw)

    core_overlap = core_tender_keywords & snippet_keywords
    core_match_ratio = len(core_overlap) / max(len(core_tender_keywords), 1) if core_tender_keywords else 0

    # 3. 招标关键词覆盖率（片段覆盖了多少招标关键词，用对数压缩避免大词表导致分数过低）
    tender_coverage = len(overlap) / len(tender_keywords)

    # 综合评分：相关占比50% + 核心词匹配30% + 覆盖率20%
    score = int(snippet_relevance_ratio * 50 + core_match_ratio * 30 + tender_coverage * 20)
    # 因为 tender_coverage 天然偏低（招标文件关键词多），额外加成
    if len(overlap) >= 5:
        score += 10
    if len(core_overlap) >= 3:
        score += 10
    score = min(100, score)

    # 领域污染惩罚
    contamination = detect_domain_contamination(snippet_content, tender_keywords)
    penalty = 0
    for domain, words, severity in contamination:
        if severity == "严重":
            penalty += 25
        elif severity == "中等":
            penalty += 15
        else:
            penalty += 5
    score = max(0, score - penalty)

    # 确定等级
    if score >= 60:
        level = "高"
    elif score >= 35:
        level = "中"
    else:
        level = "低"

    details = {
        "tender_keywords_count": len(tender_keywords),
        "snippet_keywords_count": len(snippet_keywords),
        "overlap_count": len(overlap),
        "snippet_relevance_ratio": round(snippet_relevance_ratio, 2),
        "core_tender_keywords_count": len(core_tender_keywords),
        "core_overlap_count": len(core_overlap),
        "core_match_ratio": round(core_match_ratio, 2),
        "tender_coverage": round(tender_coverage, 2),
        "contamination": [(d, ws, s) for d, ws, s in contamination],
        "penalty": penalty,
        "overlap_keywords": sorted(list(overlap))[:20],
        "core_overlap_keywords": sorted(list(core_overlap))[:15],
    }

    return score, level, details


def check_relevance(snippet_path, tender_path, project_name=None):
    """检查片段与招标文件的相关性

    Args:
        snippet_path: 改写后的片段文件路径
        tender_path: 招标文件解析结果路径
        project_name: 当前项目名

    Returns:
        (score, level, details)
    """
    with open(snippet_path, 'r', encoding='utf-8') as f:
        snippet_content = f.read()

    with open(tender_path, 'r', encoding='utf-8') as f:
        tender_content = f.read()

    tender_keywords = extract_keywords_from_tender(tender_content)
    snippet_keywords = extract_keywords_from_snippet(snippet_content)

    score, level, details = calculate_relevance(
        tender_keywords, snippet_keywords, snippet_content, tender_content
    )

    return score, level, details


def check_dir_relevance(snippet_dir, tender_path, project_name=None):
    """批量检查目录下所有片段的相关性"""
    dir_path = Path(snippet_dir)
    if not dir_path.exists():
        print(f'错误: 目录不存在: {snippet_dir}')
        return

    md_files = list(dir_path.rglob('*.md'))
    if not md_files:
        print(f'目录中没有 .md 文件: {snippet_dir}')
        return

    # 读取招标文件关键词（只读一次）
    with open(tender_path, 'r', encoding='utf-8') as f:
        tender_content = f.read()
    tender_keywords = extract_keywords_from_tender(tender_content)

    print(f'招标文件关键词: {len(tender_keywords)} 个')
    print(f'扫描片段数: {len(md_files)}\n')

    results = []
    for md_file in sorted(md_files):
        with open(md_file, 'r', encoding='utf-8') as f:
            snippet_content = f.read()

        snippet_keywords = extract_keywords_from_snippet(snippet_content)
        score, level, details = calculate_relevance(
            tender_keywords, snippet_keywords, snippet_content, tender_content
        )

        results.append((str(md_file), score, level, details))

    # 按评分降序排列
    results.sort(key=lambda x: x[1], reverse=True)

    print(f'{"评分":<6} {"等级":<4} {"文件"}')
    print('-' * 100)

    high_count = 0
    mid_count = 0
    low_count = 0

    for fpath, score, level, details in results:
        icon = "✓" if level == "高" else ("⚠" if level == "中" else "✗")
        print(f'{score:<6} {icon} {level:<4} {os.path.basename(fpath)}')
        if level == "高":
            high_count += 1
        elif level == "中":
            mid_count += 1
        else:
            low_count += 1

    print(f'\n汇总: 高相关性 {high_count} 个 | 中相关性 {mid_count} 个 | 低相关性 {low_count} 个')
    print(f'建议: 高→可直接改写使用 | 中→需大幅改写 | 低→建议弃用，从零编写')

    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'check':
        if len(sys.argv) < 4:
            print('用法: relevance_check.py check <片段.md> --tender <招标文件解析结果.md> [--project <项目名>]')
            sys.exit(1)

        snippet_path = sys.argv[2]
        tender_path = None
        project_name = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--tender' and i + 1 < len(args):
                tender_path = args[i + 1]; i += 2
            elif args[i] == '--project' and i + 1 < len(args):
                project_name = args[i + 1]; i += 2
            else:
                i += 1

        if not tender_path:
            print('错误: 必须指定 --tender')
            sys.exit(1)

        score, level, details = check_relevance(snippet_path, tender_path, project_name)

        print(f'片段文件: {snippet_path}')
        print(f'招标文件: {tender_path}')
        if project_name:
            print(f'当前项目: {project_name}')
        print()

        icon = "✓" if level == "高" else ("⚠" if level == "中" else "✗")
        print(f'{icon} 相关性评分: {score}/100 (等级: {level})')
        print()

        print(f'招标文件关键词: {details["tender_keywords_count"]} 个 (核心词: {details["core_tender_keywords_count"]} 个)')
        print(f'片段关键词: {details["snippet_keywords_count"]} 个')
        print(f'重合关键词: {details["overlap_count"]} 个 (核心词重合: {details["core_overlap_count"]} 个)')
        print(f'片段关键词相关占比: {details["snippet_relevance_ratio"]} (权重50%)')
        print(f'核心词匹配率: {details["core_match_ratio"]} (权重30%)')
        print(f'招标关键词覆盖率: {details["tender_coverage"]} (权重20%)')
        print()

        if details.get("core_overlap_keywords"):
            print(f'核心匹配词: {", ".join(details["core_overlap_keywords"])}')
        if details["overlap_keywords"]:
            print(f'全部重合词: {", ".join(details["overlap_keywords"])}')
        print()

        if details["contamination"]:
            print(f'⚠ 跨领域污染 (扣分: {details["penalty"]}):')
            for domain, words, severity in details["contamination"]:
                print(f'  [{severity}] {domain}: {", ".join(words)}')
            print()

        if level == "高":
            print('✓ 相关性高，片段可直接改写使用。')
        elif level == "中":
            print('⚠ 相关性中等，片段需大幅改写，删除不相关内容，补充项目特定内容。')
        else:
            print('✗ 相关性低，建议弃用此片段，从零编写。')
            print('  原因: 片段内容与招标项目需求关联度不足，强行使用会产生大量无关内容。')

    elif cmd == 'check-dir':
        if len(sys.argv) < 4:
            print('用法: relevance_check.py check-dir <片段目录> --tender <招标文件解析结果.md> [--project <项目名>]')
            sys.exit(1)

        snippet_dir = sys.argv[2]
        tender_path = None
        project_name = None

        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == '--tender' and i + 1 < len(args):
                tender_path = args[i + 1]; i += 2
            elif args[i] == '--project' and i + 1 < len(args):
                project_name = args[i + 1]; i += 2
            else:
                i += 1

        if not tender_path:
            print('错误: 必须指定 --tender')
            sys.exit(1)

        check_dir_relevance(snippet_dir, tender_path, project_name)

    else:
        print(f'未知命令: {cmd}')
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
