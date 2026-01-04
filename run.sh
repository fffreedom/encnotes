#!/bin/bash

# 数学笔记启动脚本

echo "🚀 启动数学笔记应用..."

# 检查Python版本
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到Python3，请先安装Python 3.8或更高版本"
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
python3 -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  未安装依赖，正在安装..."
    pip3 install -r requirements.txt
fi

# 运行应用
echo "✨ 启动应用..."
python3 main.py
