# 快速打包指南

## 🚀 5分钟打包你的应用

### 第一步：安装依赖

```bash
# 安装 Python 打包工具
pip3 install pyinstaller pillow

# 安装 DMG 创建工具
brew install create-dmg
```

### 第二步：生成图标（可选）

```bash
cd build_scripts

# 使用默认图标
python3 create_icon.py

# 或使用自定义图标（需要 1024x1024 PNG）
python3 create_icon.py your_icon.png
```

### 第三步：打包应用

```bash
# 给脚本添加执行权限（首次需要）
chmod +x build_dmg.sh build_app.sh

# 构建 DMG 安装包
./build_dmg.sh
```

### 第四步：测试安装

```bash
# 打开生成的 DMG
open ../dist/MathNotes-3.4.0.dmg

# 拖拽应用到 Applications 文件夹
# 从启动台启动应用测试
```

## 🎯 快速测试（不创建 DMG）

如果只想快速测试应用：

```bash
cd build_scripts
./build_app.sh

# 直接运行生成的应用
open ../dist/MathNotes.app
```

## 📝 常见问题

### Q: 提示 "command not found: brew"
A: 先安装 Homebrew：
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Q: 提示 "command not found: pyinstaller"
A: 安装 PyInstaller：
```bash
pip3 install pyinstaller
```

### Q: 应用打包失败
A: 检查是否所有依赖都已安装：
```bash
pip3 install -r ../requirements.txt
```

### Q: DMG 创建失败
A: 确保已安装 create-dmg：
```bash
brew install create-dmg
```

## 📦 输出文件

成功后，你会得到：

```
dist/
├── MathNotes.app           # macOS 应用（可直接运行）
└── MathNotes-3.4.0.dmg     # DMG 安装包（用于分发）
```

## 🎉 完成！

现在你可以：
- 双击 `MathNotes.app` 直接运行
- 分享 `MathNotes-3.4.0.dmg` 给其他用户
- 上传到 GitHub Releases 供下载

---

**需要更多帮助？** 查看完整的 [构建指南](README.md)
