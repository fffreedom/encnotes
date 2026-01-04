# 安装指南

## 快速开始

### 方法一：使用启动脚本（推荐）

1. 打开终端，进入项目目录：
```bash
cd /Users/danahan/project/notes
```

2. 给启动脚本添加执行权限：
```bash
chmod +x run.sh
```

3. 运行启动脚本：
```bash
./run.sh
```

启动脚本会自动检查并安装依赖，然后启动应用。

### 方法二：手动安装

1. 安装依赖：
```bash
pip3 install -r requirements.txt
```

2. 运行应用：
```bash
python3 main.py
```

## 依赖说明

本应用需要以下Python包：

- **PyQt6** (>=6.4.0): GUI框架
- **matplotlib** (>=3.6.0): 用于渲染LaTeX公式
- **lxml** (>=4.9.0): 用于解析MathML

## 系统要求

- macOS 10.14 或更高版本
- Python 3.8 或更高版本
- 至少 100MB 可用磁盘空间

## 故障排除

### 问题1: 提示"command not found: python3"

**解决方案**: 安装Python 3
```bash
# 使用Homebrew安装
brew install python3
```

### 问题2: pip安装依赖失败

**解决方案**: 升级pip
```bash
pip3 install --upgrade pip
```

### 问题3: PyQt6安装失败

**解决方案**: 
```bash
# 先安装必要的系统依赖
brew install qt6

# 然后重新安装PyQt6
pip3 install PyQt6
```

### 问题4: matplotlib渲染中文乱码

**解决方案**: 
```bash
# 安装中文字体支持
pip3 install matplotlib --upgrade
```

## 卸载

如果需要卸载应用：

1. 删除应用目录：
```bash
rm -rf /Users/danahan/project/notes
```

2. 删除数据目录（可选，会删除所有笔记）：
```bash
rm -rf ~/.mathnotes
```

3. 卸载Python依赖（可选）：
```bash
pip3 uninstall PyQt6 matplotlib lxml
```

## 开发环境设置

如果你想参与开发：

1. 克隆项目
2. 创建虚拟环境：
```bash
python3 -m venv venv
source venv/bin/activate
```

3. 安装开发依赖：
```bash
pip install -r requirements.txt
```

4. 运行应用：
```bash
python main.py
```

## 更多帮助

如有问题，请查看 [README.md](README.md) 或提交Issue。
