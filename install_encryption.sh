#!/bin/bash

# 端到端加密功能依赖安装脚本

echo "🔐 安装端到端加密功能所需的依赖..."
echo ""

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python 版本: $python_version"
echo ""

# 安装依赖
echo "📦 安装依赖包..."
pip3 install cryptography>=41.0.0 keyring>=24.0.0

# 检查安装结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 依赖安装成功！"
    echo ""
    echo "已安装的包："
    pip3 list | grep -E "(cryptography|keyring)"
    echo ""
    echo "🎉 现在可以使用端到端加密功能了！"
    echo ""
    echo "使用方法："
    echo "1. 运行应用: python3 main.py"
    echo "2. 首次启动时设置密码"
    echo "3. 所有笔记将自动加密"
    echo ""
    echo "详细说明请查看: ENCRYPTION_GUIDE.md"
else
    echo ""
    echo "❌ 依赖安装失败"
    echo ""
    echo "请尝试手动安装："
    echo "pip3 install cryptography keyring"
    exit 1
fi
