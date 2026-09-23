#!/bin/bash
# ============================================================
# 小波标书助手V9.0 macOS 环境配置脚本 v1.0
# 功能：检查依赖、安装 Python 库、检测中文字体、修补脚本路径
# 用法：bash macos_setup.sh
# ============================================================

set -e

echo "========================================"
echo "  小波标书助手V9.0 macOS 环境配置"
echo "========================================"
echo ""

echo "[1/5] 检查 Python 3..."
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    echo "  ✓ 已安装: $PY_VERSION"
    PYTHON_CMD="python3"
else
    echo "  ✗ 未找到 python3，正在尝试安装..."
    if command -v brew &>/dev/null; then
        brew install python@3.12
        PYTHON_CMD="python3"
        echo "  ✓ 安装完成: $(python3 --version)"
    else
        echo "  ✗ 未找到 Homebrew，请先安装: https://brew.sh"
        echo "  或手动安装 Python 3: https://python.org"
        exit 1
    fi
fi
echo ""

echo "[2/5] 安装 Python 依赖库..."
PIP_ARGS="--quiet"
echo "  安装核心依赖 (python-docx, pdfplumber, openpyxl, PyPDF2)..."
$PYTHON_CMD -m pip install $PIP_ARGS python-docx pdfplumber openpyxl PyPDF2 2>/dev/null || {
    echo "  ⚠ 部分核心依赖安装失败，尝试逐个安装..."
    for pkg in python-docx pdfplumber openpyxl PyPDF2; do
        $PYTHON_CMD -m pip install $PIP_ARGS "$pkg" 2>/dev/null && echo "    ✓ $pkg" || echo "    ✗ $pkg (失败)"
    done
}
echo "  安装 MarkItDown (二级解析，可选)..."
$PYTHON_CMD -m pip install $PIP_ARGS "markitdown[all]" 2>/dev/null && echo "    ✓ markitdown" || echo "    ⚠ markitdown 安装失败，二级解析将不可用"
echo "  ✓ 依赖安装完成"
echo ""

echo "[3/5] 检测中文字体..."
FONT_AVAILABLE=""
MAC_FONTS=("Songti SC" "STSong" "SimSun" "PingFang SC" "Heiti SC")
if command -v fc-list &>/dev/null; then
    INSTALLED_FONTS=$(fc-list : family 2>/dev/null)
else
    INSTALLED_FONTS=$(ls "/System/Library/Fonts/" "/Library/Fonts/" ~/Library/Fonts/ 2>/dev/null | tr '\n' '|')
fi
for font in "${MAC_FONTS[@]}"; do
    if echo "$INSTALLED_FONTS" | grep -iq "$font" 2>/dev/null; then
        FONT_AVAILABLE="$font"
        echo "  ✓ 检测到字体: $font"
        break
    fi
done
if [ -z "$FONT_AVAILABLE" ]; then
    echo "  ⚠ 未检测到专用中文字体，将使用默认字体"
    echo "  建议: macOS 自带 Songti SC，通常无需额外安装"
    FONT_AVAILABLE="Songti SC"
    echo "  → 默认使用: $FONT_AVAILABLE"
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FONT_CONFIG="$SCRIPT_DIR/macos_font_config.json"
cat > "$FONT_CONFIG" << EOF
{
    "platform": "macos",
    "default_font": "$FONT_AVAILABLE",
    "font_mapping": {
        "宋体": "$FONT_AVAILABLE",
        "SimSun": "$FONT_AVAILABLE",
        "仿宋": "STFangsong",
        "FangSong": "STFangsong",
        "黑体": "STHeiti",
        "SimHei": "STHeiti",
        "楷体": "STKaiti",
        "KaiTi": "STKaiti",
        "微软雅黑": "PingFang SC",
        "Microsoft YaHei": "PingFang SC"
    },
    "note": "macOS 字体映射配置，convert_to_word.py 自动加载此文件"
}
EOF
echo "  ✓ 字体配置已保存: $FONT_CONFIG"
echo ""

echo "[4/5] 检查技能目录..."
CONFIG_DIRS=("$HOME/.config/TeleAgent/skills" "$HOME/.local/share/TeleAgent/skills" "$HOME/Library/Application Support/TeleAgent/skills")
SKILLS_DIR=""
for dir in "${CONFIG_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        SKILLS_DIR="$dir"
        echo "  ✓ 找到技能目录: $SKILLS_DIR"
        break
    fi
done
if [ -z "$SKILLS_DIR" ]; then
    echo "  ⚠ 未找到 TeleAgent 技能目录"
    echo "  如果通过其他方式安装，请设置环境变量:"
    echo "    export TELEAGENT_CONFIG_DIR=<你的配置目录>"
else
    if [ -d "$SKILLS_DIR/xc-doc-parser" ]; then
        echo "  ✓ xc-doc-parser 技能已安装（三级解析可用）"
    else
        echo "  ⚠ xc-doc-parser 技能未安装（三级解析不可用，一级和二级正常）"
    fi
fi
echo ""

echo "[5/5] 验证安装..."
echo ""
$PYTHON_CMD -c "
import sys
modules = ['docx', 'pdfplumber', 'openpyxl', 'PyPDF2']
ok = 0
fail = 0
for m in modules:
    try:
        __import__(m)
        print(f'  ✓ {m}')
        ok += 1
    except ImportError:
        print(f'  ✗ {m} (未安装)')
        fail += 1
try:
    from markitdown import MarkItDown
    print('  ✓ markitdown')
    ok += 1
except ImportError:
    print('  ⚠ markitdown (未安装，二级解析不可用)')
print(f'')
print(f'  结果: {ok} 个可用, {fail} 个缺失')
" 2>/dev/null
echo ""
echo "========================================"
echo "  配置完成！"
echo "========================================"
echo ""
echo "使用方法:"
echo "  $PYTHON_CMD scripts/parse_bid_files.py <文件路径>"
echo "  $PYTHON_CMD scripts/convert_to_word.py <输入.md> <输出.docx> --template <模板.docx>"
echo "  $PYTHON_CMD scripts/template_extractor.py <模板.docx>"
echo ""
echo "注意:"
echo "  - macOS 上请使用 python3 命令"
echo "  - 字体已自动映射为 macOS 兼容字体"
echo "  - 字体配置文件: $FONT_CONFIG"
echo ""
