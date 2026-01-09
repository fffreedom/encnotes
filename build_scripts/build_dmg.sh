#!/bin/bash
# DMG 打包脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  encnotes DMG 打包脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 配置变量
APP_NAME="encnotes"
APP_DISPLAY_NAME="加密笔记"
VERSION="3.4.0"
DMG_NAME="${APP_NAME}-${VERSION}"
BUILD_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="${BUILD_DIR}/build_scripts"
DIST_DIR="${SCRIPT_DIR}/dist"
DMG_DIR="${BUILD_DIR}/dmg_build"
SPEC_FILE="${SCRIPT_DIR}/${APP_NAME}.spec"

echo -e "${YELLOW}项目目录: ${BUILD_DIR}${NC}"
echo -e "${YELLOW}输出目录: ${DIST_DIR}${NC}"

# 1. 清理旧的构建文件
echo -e "\n${GREEN}[1/6] 清理旧的构建文件...${NC}"

# 先卸载任何挂载的 DMG
echo -e "${YELLOW}卸载挂载的 DMG 镜像...${NC}"
for mount_point in $(hdiutil info | grep -E "^/dev/disk" | grep -oE "/Volumes/[^,]+" | sort -u); do
    if [[ "$mount_point" == *"encnotes"* ]] || [[ "$mount_point" == *"dmg"* ]]; then
        echo -e "${YELLOW}卸载: $mount_point${NC}"
        hdiutil detach "$mount_point" 2>/dev/null || true
    fi
done

# 强制删除构建目录
echo -e "${YELLOW}删除构建文件...${NC}"
rm -rf "${BUILD_DIR}/build" 2>/dev/null || true
rm -rf "${DIST_DIR}" 2>/dev/null || true
rm -rf "${DMG_DIR}" 2>/dev/null || true

# 再次尝试删除，确保彻底清理
sleep 1
rm -rf "${BUILD_DIR}/build" 2>/dev/null || true
rm -rf "${DIST_DIR}" 2>/dev/null || true
rm -rf "${DMG_DIR}" 2>/dev/null || true

# 创建新的目录
mkdir -p "${DIST_DIR}"
mkdir -p "${DMG_DIR}"

# 2. 检查依赖
echo -e "\n${GREEN}[2/6] 检查依赖...${NC}"
if ! command -v pyinstaller &> /dev/null; then
    echo -e "${YELLOW}安装 PyInstaller...${NC}"
    pip3 install pyinstaller
fi

if ! command -v create-dmg &> /dev/null; then
    echo -e "${YELLOW}安装 create-dmg...${NC}"
    brew install create-dmg
fi

# 3. 使用 PyInstaller 打包应用
echo -e "\n${GREEN}[3/6] 使用 PyInstaller 打包应用...${NC}"
cd "${BUILD_DIR}/build_scripts"
pyinstaller --clean --noconfirm "${SPEC_FILE}"

# 检查是否成功生成 .app
if [ ! -d "${DIST_DIR}/${APP_NAME}.app" ]; then
    echo -e "${RED}错误: 应用打包失败${NC}"
    exit 1
fi

echo -e "${GREEN}应用打包成功: ${DIST_DIR}/${APP_NAME}.app${NC}"

# 4. 复制应用到 DMG 临时目录
echo -e "\n${GREEN}[4/6] 准备 DMG 内容...${NC}"
cp -R "${DIST_DIR}/${APP_NAME}.app" "${DMG_DIR}/"

# 注意：不需要手动创建 Applications 符号链接
# create-dmg 会通过 --app-drop-link 参数自动创建

# 5. 创建 DMG
echo -e "\n${GREEN}[5/6] 创建 DMG 镜像...${NC}"
create-dmg \
  --volname "${APP_DISPLAY_NAME}" \
  --volicon "${BUILD_DIR}/build_scripts/icon.icns" \
  --window-pos 200 120 \
  --window-size 800 400 \
  --icon-size 100 \
  --app-drop-link 600 185 \
  --icon "${APP_NAME}.app" 200 190 \
  --hide-extension "${APP_NAME}.app" \
  --no-internet-enable \
  "${DIST_DIR}/${DMG_NAME}.dmg" \
  "${DMG_DIR}/"

# 6. 清理临时文件
echo -e "\n${GREEN}[6/6] 清理临时文件...${NC}"

# 先卸载任何挂载的 DMG
echo -e "${YELLOW}卸载挂载的 DMG 镜像...${NC}"
for mount_point in $(hdiutil info | grep -E "^/dev/disk" | grep -oE "/Volumes/[^,]+" | sort -u); do
    if [[ "$mount_point" == *"encnotes"* ]] || [[ "$mount_point" == *"dmg"* ]]; then
        echo -e "${YELLOW}卸载: $mount_point${NC}"
        hdiutil detach "$mount_point" 2>/dev/null || true
    fi
done

sleep 1

# 删除临时目录
rm -rf "${DMG_DIR}" 2>/dev/null || true
rm -rf "${BUILD_DIR}/build" 2>/dev/null || true

# 完成
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  打包完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}DMG 文件位置: ${DIST_DIR}/${DMG_NAME}.dmg${NC}"
echo -e "${GREEN}文件大小: $(du -h "${DIST_DIR}/${DMG_NAME}.dmg" | cut -f1)${NC}"
echo -e "\n${YELLOW}安装说明:${NC}"
echo -e "1. 双击打开 ${DMG_NAME}.dmg"
echo -e "2. 将 ${APP_DISPLAY_NAME} 拖拽到 Applications 文件夹"
echo -e "3. 从启动台或 Applications 文件夹启动应用"
echo ""
