# 构建和打包指南

本目录包含将 MathNotes 应用打包为 macOS DMG 安装包的所有脚本和配置文件。

## 📁 文件说明

- `MathNotes.spec` - PyInstaller 配置文件
- `build_dmg.sh` - 完整的 DMG 打包脚本
- `build_app.sh` - 快速构建脚本（仅打包 .app）
- `create_icon.py` - 图标生成工具
- `icon.icns` - 应用图标文件
- `README.md` - 本文档

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装 Python 打包工具
pip3 install pyinstaller pillow

# 安装 DMG 创建工具（使用 Homebrew）
brew install create-dmg
```

### 2. 生成应用图标（可选）

如果你有自己的图标（1024x1024 PNG）：

```bash
cd build_scripts
python3 create_icon.py your_icon.png
```

如果没有，脚本会自动生成一个默认图标：

```bash
python3 create_icon.py
```

### 3. 构建应用

#### 方式一：快速构建（仅生成 .app）

适合开发测试：

```bash
cd build_scripts
chmod +x build_app.sh
./build_app.sh
```

生成的应用位于：`dist/MathNotes.app`

#### 方式二：完整打包（生成 DMG）

适合发布分发：

```bash
cd build_scripts
chmod +x build_dmg.sh
./build_dmg.sh
```

生成的 DMG 位于：`dist/MathNotes-3.3.0.dmg`

## 📦 打包流程详解

### 第一步：PyInstaller 打包

PyInstaller 将 Python 应用及其依赖打包成独立的 macOS 应用：

```bash
pyinstaller --clean --noconfirm MathNotes.spec
```

**配置说明**（MathNotes.spec）：

- `hiddenimports`: 显式声明需要打包的模块
- `excludes`: 排除不需要的模块（减小体积）
- `icon`: 应用图标
- `bundle_identifier`: 应用唯一标识符
- `info_plist`: macOS 应用元数据

### 第二步：创建 DMG

使用 `create-dmg` 工具创建美观的安装镜像：

```bash
create-dmg \
  --volname "数学笔记" \
  --window-size 800 400 \
  --icon-size 100 \
  --app-drop-link 600 185 \
  "MathNotes-3.3.0.dmg" \
  "dmg_build/"
```

**DMG 特性**：

- 自定义窗口大小和位置
- 包含 Applications 文件夹快捷方式
- 拖拽安装界面
- 自定义背景图（可选）

## 🔧 自定义配置

### 修改应用信息

编辑 `MathNotes.spec` 文件：

```python
app = BUNDLE(
    coll,
    name='MathNotes.app',
    bundle_identifier='com.mathnotes.app',  # 修改应用标识
    version='3.3.0',                         # 修改版本号
    info_plist={
        'CFBundleDisplayName': '数学笔记',   # 修改显示名称
        # ... 其他配置
    },
)
```

### 修改 DMG 外观

编辑 `build_dmg.sh` 文件：

```bash
create-dmg \
  --volname "你的应用名称" \          # DMG 卷名
  --window-size 800 400 \            # 窗口大小
  --icon-size 100 \                  # 图标大小
  --background "background.png" \    # 自定义背景图
  # ...
```

### 添加自定义文件

在 `MathNotes.spec` 中添加：

```python
datas=[
    ('../*.py', '.'),
    ('../resources', 'resources'),  # 添加资源文件夹
    ('../README.md', '.'),          # 添加文档
],
```

## 🐛 常见问题

### 问题 1: PyInstaller 找不到模块

**解决方案**：在 `MathNotes.spec` 的 `hiddenimports` 中添加缺失的模块：

```python
hiddenimports=[
    'your_missing_module',
],
```

### 问题 2: 应用启动后闪退

**解决方案**：

1. 在终端中直接运行应用查看错误：
   ```bash
   ./dist/MathNotes.app/Contents/MacOS/MathNotes
   ```

2. 检查是否缺少依赖库或资源文件

### 问题 3: DMG 创建失败

**解决方案**：

1. 确保已安装 `create-dmg`：
   ```bash
   brew install create-dmg
   ```

2. 检查磁盘空间是否充足

3. 删除旧的 DMG 文件后重试

### 问题 4: 应用体积过大

**解决方案**：

1. 在 `MathNotes.spec` 中排除不需要的模块：
   ```python
   excludes=[
       'tkinter',
       'unittest',
       'test',
   ],
   ```

2. 启用 UPX 压缩：
   ```python
   upx=True,
   ```

3. 使用虚拟环境，只安装必要的依赖

## 📊 打包后的文件结构

```
dist/
├── MathNotes.app/              # macOS 应用包
│   ├── Contents/
│   │   ├── MacOS/
│   │   │   └── MathNotes       # 可执行文件
│   │   ├── Resources/
│   │   │   ├── icon.icns       # 应用图标
│   │   │   └── ...             # 其他资源
│   │   ├── Frameworks/         # 依赖库
│   │   └── Info.plist          # 应用元数据
│   └── ...
└── MathNotes-3.3.0.dmg         # DMG 安装包
```

## 🔐 代码签名（可选）

如果要发布到 Mac App Store 或避免"未验证的开发者"警告，需要进行代码签名：

### 1. 获取开发者证书

从 Apple Developer 网站获取开发者证书。

### 2. 签名应用

```bash
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" \
  dist/MathNotes.app
```

### 3. 公证应用

```bash
# 创建 DMG 后公证
xcrun notarytool submit MathNotes-3.3.0.dmg \
  --apple-id "your@email.com" \
  --password "app-specific-password" \
  --team-id "TEAM_ID"
```

### 4. 验证签名

```bash
codesign --verify --deep --strict --verbose=2 dist/MathNotes.app
spctl -a -t exec -vv dist/MathNotes.app
```

## 📝 发布检查清单

发布前请确认：

- [ ] 更新版本号（MathNotes.spec 和 build_dmg.sh）
- [ ] 测试应用所有功能正常
- [ ] 检查应用图标显示正确
- [ ] 测试 DMG 安装流程
- [ ] 在干净的系统上测试应用
- [ ] 准备发布说明（CHANGELOG.md）
- [ ] 代码签名和公证（如需要）
- [ ] 准备应用截图和宣传材料

## 🚢 分发方式

### 1. 直接下载

将 DMG 文件上传到：
- GitHub Releases
- 自己的网站
- 云存储服务

### 2. Homebrew Cask

创建 Homebrew Cask 配方：

```ruby
cask "mathnotes" do
  version "3.3.0"
  sha256 "..."
  
  url "https://example.com/MathNotes-#{version}.dmg"
  name "MathNotes"
  desc "数学笔记应用"
  homepage "https://example.com"
  
  app "MathNotes.app"
end
```

### 3. Mac App Store

需要：
- Apple Developer 账号
- 完整的代码签名和公证
- 遵守 App Store 审核指南

## 📚 参考资料

- [PyInstaller 文档](https://pyinstaller.org/)
- [create-dmg GitHub](https://github.com/create-dmg/create-dmg)
- [macOS 应用打包指南](https://developer.apple.com/documentation/bundleresources)
- [代码签名指南](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)

## 💡 提示

1. **开发阶段**：使用 `build_app.sh` 快速构建测试
2. **发布阶段**：使用 `build_dmg.sh` 创建完整的 DMG
3. **持续集成**：可以将构建脚本集成到 CI/CD 流程中
4. **版本管理**：每次发布前更新版本号和 CHANGELOG

---

**需要帮助？** 查看主项目的 README.md 或提交 Issue。
