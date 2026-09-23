#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS 兼容模块 v1.0

为小波标书助手V9.0各脚本提供跨平台兼容支持。
在 macOS 环境下自动处理：
1. Python 命令差异（python → python3）
2. 中文字体映射（宋体 → Songti SC / STSong）
3. 技能目录路径查找
4. 子进程调用适配

使用方式：
    from macos_compat import get_python_cmd, get_font, get_skills_dir, run_subprocess

    # 获取当前平台的 Python 命令
    py_cmd = get_python_cmd()

    # 获取中文字体（自动映射）
    font = get_font('宋体')  # macOS 上返回 'Songti SC'

    # 获取技能目录
    skills_dir = get_skills_dir()

    # 运行子进程（自动适配 python 命令）
    result = run_subprocess(['python', 'script.py'], ...)
"""

import sys
import os
import json
import platform
import subprocess


# ============================================================
# 平台检测
# ============================================================

def is_macos():
    """检测是否为 macOS"""
    return sys.platform == 'darwin'


def is_windows():
    """检测是否为 Windows"""
    return sys.platform == 'win32'


def is_linux():
    """检测是否为 Linux"""
    return sys.platform.startswith('linux')


def get_platform_name():
    """获取平台名称"""
    if is_macos():
        return 'macos'
    elif is_windows():
        return 'windows'
    elif is_linux():
        return 'linux'
    return 'unknown'


# ============================================================
# Python 命令适配
# ============================================================

def get_python_cmd():
    """获取当前平台的 Python 命令

    Windows: 'python'
    macOS/Linux: 'python3'（优先）或 'python'
    """
    if is_windows():
        return 'python'

    # macOS / Linux: 优先 python3
    try:
        subprocess.run(['python3', '--version'],
                       capture_output=True, timeout=5)
        return 'python3'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 退回到 python
    try:
        subprocess.run(['python', '--version'],
                       capture_output=True, timeout=5)
        return 'python'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return sys.executable  # 最终回退：使用当前解释器


def run_subprocess(cmd_list, **kwargs):
    """运行子进程，自动适配 Python 命令

    将 cmd_list 中的 'python' 替换为当前平台的正确命令。
    """
    py_cmd = get_python_cmd()
    adapted = [py_cmd if c == 'python' else c for c in cmd_list]
    return subprocess.run(adapted, **kwargs)


# ============================================================
# 字体映射
# ============================================================

# macOS 中文字体映射表
MACOS_FONT_MAP = {
    '宋体': 'Songti SC',
    'SimSun': 'Songti SC',
    '仿宋': 'STFangsong',
    'FangSong': 'STFangsong',
    '黑体': 'STHeiti',
    'SimHei': 'STHeiti',
    '楷体': 'STKaiti',
    'KaiTi': 'STKaiti',
    '微软雅黑': 'PingFang SC',
    'Microsoft YaHei': 'PingFang SC',
    '等线': 'PingFang SC',
    'DengXian': 'PingFang SC',
}

# Linux 中文字体映射表（常见安装）
LINUX_FONT_MAP = {
    '宋体': 'Noto Serif CJK SC',
    'SimSun': 'Noto Serif CJK SC',
    '黑体': 'Noto Sans CJK SC',
    'SimHei': 'Noto Sans CJK SC',
    '微软雅黑': 'Noto Sans CJK SC',
    'Microsoft YaHei': 'Noto Sans CJK SC',
    '仿宋': 'Noto Serif CJK SC',
    '楷体': 'Noto Serif CJK SC',
}

# Windows 字体（原样返回）
WINDOWS_FONT_MAP = {}


def _load_font_config():
    """从 macos_setup.sh 生成的配置文件加载字体映射"""
    config_path = os.path.join(os.path.dirname(__file__), 'macos_font_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('font_mapping', {})
        except (json.JSONDecodeError, IOError):
            pass
    return None


def get_font(font_name):
    """获取跨平台兼容的字体名称

    Args:
        font_name: 原始字体名称（如 '宋体', 'SimSun'）
    Returns:
        当前平台对应的字体名称
    """
    if is_windows():
        return font_name  # Windows 上原样返回

    # 先尝试加载用户配置（macos_setup.sh 生成的）
    user_config = _load_font_config()
    if user_config and font_name in user_config:
        return user_config[font_name]

    # 使用内置映射
    if is_macos():
        return MACOS_FONT_MAP.get(font_name, font_name)
    elif is_linux():
        return LINUX_FONT_MAP.get(font_name, font_name)

    return font_name


def get_default_font():
    """获取当前平台的默认正文字体"""
    if is_windows():
        return '宋体'
    elif is_macos():
        return 'Songti SC'
    elif is_linux():
        return 'Noto Serif CJK SC'
    return '宋体'


def adapt_font_dict(fmt):
    """适配格式字典中的字体名称

    遍历 fmt 字典，将所有字体相关字段的值映射为当前平台兼容的字体。
    """
    font_keys = ['font', 'east_asia_font', 'title_font']
    for key in font_keys:
        if key in fmt and fmt[key]:
            fmt[key] = get_font(fmt[key])
    return fmt


# ============================================================
# 技能目录查找
# ============================================================

def get_skills_dir():
    """查找 TeleAgent 技能目录

    搜索顺序：
    1. 环境变量 TELEAGENT_CONFIG_DIR
    2. 平台常见路径
    3. 相对路径（脚本所在目录的上上级）
    """
    # 1. 环境变量
    env_dir = os.environ.get('TELEAGENT_CONFIG_DIR', '')
    if env_dir:
        skills_path = os.path.join(env_dir, 'skills')
        if os.path.isdir(skills_path):
            return skills_path

    # 2. 平台常见路径
    if is_macos():
        candidate_paths = [
            os.path.expanduser('~/.config/TeleAgent/skills'),
            os.path.expanduser('~/.local/share/TeleAgent/skills'),
            os.path.expanduser('~/Library/Application Support/TeleAgent/skills'),
        ]
    elif is_windows():
        candidate_paths = [
            os.path.join(os.environ.get('APPDATA', ''), 'TeleAgent', 'skills'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'TeleAgent', 'skills'),
            os.path.expanduser('~/.config/TeleAgent/skills'),
        ]
    else:  # Linux
        candidate_paths = [
            os.path.expanduser('~/.config/TeleAgent/skills'),
            os.path.expanduser('~/.local/share/TeleAgent/skills'),
        ]

    for path in candidate_paths:
        if os.path.isdir(path):
            return path

    # 3. 相对路径（脚本目录的上上级）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    relative_path = os.path.normpath(os.path.join(script_dir, '..', '..'))
    if os.path.isdir(relative_path):
        return relative_path

    return None


def find_skill_script(skill_name, script_name):
    """查找其他技能的脚本文件

    Args:
        skill_name: 技能名称（如 'xc-doc-parser'）
        script_name: 脚本文件名（如 'document_parser.py'）
    Returns:
        脚本文件的完整路径，未找到返回 None
    """
    skills_dir = get_skills_dir()
    if not skills_dir:
        return None

    script_path = os.path.join(skills_dir, skill_name, 'scripts', script_name)
    if os.path.exists(script_path):
        return script_path

    return None


# ============================================================
# 路径适配
# ============================================================

def normalize_path(path):
    """规范化路径（跨平台）"""
    if not path:
        return path
    # 展开 ~ 和环境变量
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    # 规范化分隔符
    path = os.path.normpath(path)
    return path


def get_desktop_dir():
    """获取桌面目录路径"""
    if is_windows():
        return os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
    else:
        return os.path.expanduser('~/Desktop')


# ============================================================
# 自检函数
# ============================================================

def self_check():
    """运行自检，输出当前环境信息"""
    print("=" * 50)
    print("  小波标书助手V9.0 - 跨平台兼容性自检")
    print("=" * 50)
    print()

    # 平台信息
    print(f"操作系统: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"平台标识: {get_platform_name()}")
    print()

    # Python 命令
    py_cmd = get_python_cmd()
    print(f"Python 命令: {py_cmd}")
    print()

    # 字体
    default_font = get_default_font()
    print(f"默认字体: {default_font}")
    test_fonts = ['宋体', 'SimSun', '黑体', '微软雅黑']
    print("字体映射:")
    for f in test_fonts:
        mapped = get_font(f)
        status = "→" if mapped != f else "="
        print(f"  {f} {status} {mapped}")
    print()

    # 技能目录
    skills_dir = get_skills_dir()
    if skills_dir:
        print(f"技能目录: {skills_dir}")
        xc_parser = find_skill_script('xc-doc-parser', 'document_parser.py')
        if xc_parser:
            print(f"  xc-doc-parser: ✓ 已找到")
        else:
            print(f"  xc-doc-parser: ✗ 未找到（三级解析不可用）")
    else:
        print("技能目录: ✗ 未找到")
    print()

    # 依赖检查
    print("依赖检查:")
    deps = ['docx', 'pdfplumber', 'openpyxl', 'PyPDF2']
    for dep in deps:
        try:
            __import__(dep)
            print(f"  ✓ {dep}")
        except ImportError:
            print(f"  ✗ {dep} (未安装)")

    try:
        from markitdown import MarkItDown
        print(f"  ✓ markitdown")
    except ImportError:
        print(f"  ⚠ markitdown (未安装，二级解析不可用)")
    print()

    print("=" * 50)
    print("  自检完成")
    print("=" * 50)


if __name__ == '__main__':
    self_check()
