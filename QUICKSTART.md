# 快速启动指南 ⚡

## 三步启动应用

### 第一步：安装依赖

打开终端，进入项目目录并运行：

```bash
cd /Users/danahan/project/notes
pip3 install -r requirements.txt
```

### 第二步：运行应用

```bash
python3 main.py
```

或者使用启动脚本（需要先添加执行权限）：

```bash
chmod +x run.sh
./run.sh
```

### 第三步：开始使用

1. 点击"➕ 新建笔记"创建第一篇笔记
2. 在编辑器中输入内容
3. 使用 `Ctrl+L` 插入LaTeX公式
4. 使用 `Ctrl+M` 插入MathML公式

## 新功能快速体验

### 📤 导出笔记

1. 创建一篇笔记
2. 按 `Ctrl+Shift+P` 导出为PDF
3. 或按 `Ctrl+Shift+W` 导出为Word
4. 或按 `Ctrl+Shift+M` 导出为Markdown

导出的文件保存在：`~/Documents/MathNotes导出/`

### ☁️ iCloud同步

1. 点击菜单"同步" → "启用iCloud同步"
2. 按 `Ctrl+S` 立即同步到iCloud
3. 在其他Mac上安装应用并启用同步
4. 点击"从iCloud拉取"获取笔记

**注意**：需要先在系统设置中登录iCloud账户

## 常用快捷键

| 功能 | 快捷键 |
|------|--------|
| 新建笔记 | `Ctrl+N` |
| 删除笔记 | `Ctrl+D` |
| 插入LaTeX | `Ctrl+L` |
| 插入MathML | `Ctrl+M` |
| 导出PDF | `Ctrl+Shift+P` |
| 导出Word | `Ctrl+Shift+W` |
| 导出Markdown | `Ctrl+Shift+M` |
| 立即同步 | `Ctrl+S` |
| 退出应用 | `Ctrl+Q` |

## 第一个数学公式

试试插入这个经典的二次方程求根公式：

1. 按 `Ctrl+L` 打开LaTeX对话框
2. 输入：`x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}`
3. 点击"插入"

## 需要帮助？

- 📖 查看 [README.md](README.md) 了解完整功能
- 💡 查看 [EXAMPLES.md](EXAMPLES.md) 学习更多示例
- 🔧 查看 [INSTALL.md](INSTALL.md) 解决安装问题
- 📤 查看 [EXPORT_SYNC_GUIDE.md](EXPORT_SYNC_GUIDE.md) 学习导出和同步

---

**开始你的数学笔记之旅！** 🚀
