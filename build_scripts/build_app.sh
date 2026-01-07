#!/bin/bash
# 快速构建脚本 - 仅打包应用，不创建 DMG

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}快速构建 encnotes.app...${NC}"

BUILD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPEC_FILE="${BUILD_DIR}/build_scripts/encnotes.spec"

# 清理
rm -rf "${BUILD_DIR}/build"
rm -rf "${BUILD_DIR}/dist"

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}安装 PyInstaller...${NC}"
    pip3 install pyinstaller
fi

# 打包
cd "${BUILD_DIR}/build_scripts"
pyinstaller --clean --noconfirm "${SPEC_FILE}"

echo -e "${GREEN}构建完成: ${BUILD_DIR}/dist/encnotes.app${NC}"
echo -e "${YELLOW}提示: 可以直接运行 dist/encnotes.app 测试应用${NC}"
