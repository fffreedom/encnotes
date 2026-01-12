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

# 4. 代码签名（如果配置了签名身份）
echo -e "\n${GREEN}[4/7] 代码签名...${NC}"
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo -e "${YELLOW}使用签名身份: ${CODESIGN_IDENTITY}${NC}"
    
    # 签名所有框架和库
    echo -e "${YELLOW}签名框架和库...${NC}"
    find "${DIST_DIR}/${APP_NAME}.app/Contents/Frameworks" -type f -name "*.dylib" -o -name "*.so" 2>/dev/null | while read lib; do
        codesign --force --sign "$CODESIGN_IDENTITY" \
            --options runtime \
            --timestamp \
            "$lib" 2>/dev/null || true
    done
    
    # 签名应用包
    echo -e "${YELLOW}签名应用包...${NC}"
    codesign --force --deep --sign "$CODESIGN_IDENTITY" \
        --options runtime \
        --entitlements "${SCRIPT_DIR}/entitlements.plist" \
        --timestamp \
        "${DIST_DIR}/${APP_NAME}.app"
    
    # 验证签名
    echo -e "${YELLOW}验证签名...${NC}"
    codesign --verify --deep --strict --verbose=2 "${DIST_DIR}/${APP_NAME}.app"
    
    echo -e "${GREEN}代码签名完成${NC}"
else
    echo -e "${YELLOW}未配置 CODESIGN_IDENTITY 环境变量，跳过代码签名${NC}"
    echo -e "${YELLOW}提示: 设置环境变量以启用代码签名:${NC}"
    echo -e "${YELLOW}  export CODESIGN_IDENTITY=\"Developer ID Application: Your Name (TEAM_ID)\"${NC}"
fi

# 5. 复制应用到 DMG 临时目录
echo -e "\n${GREEN}[5/7] 准备 DMG 内容...${NC}"
cp -R "${DIST_DIR}/${APP_NAME}.app" "${DMG_DIR}/"

# 注意：不需要手动创建 Applications 符号链接
# create-dmg 会通过 --app-drop-link 参数自动创建

# 6. 创建 DMG
echo -e "\n${GREEN}[6/7] 创建 DMG 镜像...${NC}"
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

# 7. 清理临时文件
echo -e "\n${GREEN}[7/7] 清理临时文件...${NC}"

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
