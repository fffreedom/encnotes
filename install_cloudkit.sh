#!/bin/bash
# CloudKit依赖安装脚本

echo "================================"
echo "  安装CloudKit依赖"
echo "================================"
echo ""

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python版本: $python_version"
echo ""

# 安装PyObjC CloudKit框架
echo "正在安装 pyobjc-framework-CloudKit..."
pip3 install pyobjc-framework-CloudKit

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ CloudKit框架安装成功！"
    echo ""
    echo "================================"
    echo "  安装完成"
    echo "================================"
    echo ""
    echo "现在你可以："
    echo "1. 重启应用"
    echo "2. 在菜单中选择 '文件 -> 启用iCloud同步'"
    echo "3. 确保已在系统设置中登录iCloud账户"
    echo ""
else
    echo ""
    echo "✗ 安装失败"
    echo ""
    echo "请尝试手动安装："
    echo "  pip3 install pyobjc-framework-CloudKit"
    echo ""
    echo "或者安装完整的PyObjC："
    echo "  pip3 install pyobjc"
    echo ""
fi
