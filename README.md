# 数学笔记 - Mac风格备忘录应用

一款类似Mac备忘录的笔记软件，支持插入LaTeX和MathML数学公式。

## 功能特性

✨ **核心功能**
- 📝 Mac风格三栏布局（文件夹列表、笔记列表、编辑器）
- 📁 文件夹管理（创建、重命名、删除文件夹）
- 🎨 富文本编辑支持
- 📐 LaTeX数学公式支持
- 🔢 MathML数学公式支持
- 💾 自动保存
- ⭐ 收藏功能
- 🗑️ 回收站功能
- 📤 导出功能（PDF、Word、Markdown、HTML）
- ☁️ iCloud同步支持（CloudKit）

## 安装说明

### 1. 环境要求
- Python 3.8 或更高版本
- macOS 系统

### 2. 安装依赖

```bash
# 克隆或下载项目后，进入项目目录
cd /Users/danahan/project/notes

# 安装依赖包
pip install -r requirements.txt
```

### 3. 运行应用

```bash
python main.py
```

## 使用指南

### 基本操作

1. **创建新笔记**
   - 点击工具栏的"➕ 新建笔记"按钮
   - 或使用快捷键 `Ctrl+N`

2. **创建文件夹**
   - 点击工具栏的"📁 新建文件夹"按钮
   - 或使用快捷键 `Ctrl+Shift+N`
   - 输入文件夹名称

3. **管理文件夹**
   - 右键点击文件夹可以重命名或删除
   - 删除文件夹不会删除其中的笔记
   - 笔记会自动移动到"所有笔记"

4. **编辑笔记**
   - 在笔记列表中选择要编辑的笔记
   - 在右侧编辑器中输入内容
   - 内容会自动保存

5. **删除笔记**
   - 选中笔记后点击"🗑️ 删除"按钮
   - 或使用快捷键 `Ctrl+D`

### 导出笔记

应用支持将笔记导出为多种格式：

1. **导出为PDF**
   - 点击菜单栏"文件" → "导出" → "导出为PDF"
   - 或使用快捷键 `Ctrl+Shift+P`
   - 适合打印和分享

2. **导出为Word**
   - 点击菜单栏"文件" → "导出" → "导出为Word"
   - 或使用快捷键 `Ctrl+Shift+W`
   - 可在Microsoft Word中继续编辑

3. **导出为Markdown**
   - 点击菜单栏"文件" → "导出" → "导出为Markdown"
   - 或使用快捷键 `Ctrl+Shift+M`
   - 适合在其他Markdown编辑器中使用

4. **导出为HTML**
   - 点击菜单栏"文件" → "导出" → "导出为HTML"
   - 可在浏览器中查看

**导出位置**：所有导出的文件保存在 `~/Documents/MathNotes导出/` 文件夹中

### iCloud同步

应用支持通过iCloud同步笔记到多台Mac设备：

1. **启用同步**
   - 点击菜单栏"同步" → "启用iCloud同步"
   - 确保已在系统设置中登录iCloud账户

2. **立即同步**
   - 点击菜单栏"同步" → "立即同步"
   - 或使用快捷键 `Ctrl+S`
   - 将当前笔记上传到iCloud

3. **从iCloud拉取**
   - 点击菜单栏"同步" → "从iCloud拉取"
   - 下载并合并iCloud上的笔记

4. **自动同步**
   - 启用同步后，应用会每5分钟自动同步一次
   - 关闭应用时也会自动同步

**注意**：同步使用iCloud Drive，不需要额外配置

### 插入数学公式

#### 插入LaTeX公式

1. 点击菜单栏"插入" → "插入 LaTeX 公式"
2. 或使用快捷键 `Ctrl+L`
3. 在对话框中输入LaTeX代码（不需要包含$符号）
4. 点击"插入"按钮

**常用LaTeX示例：**
- 分数：`\frac{a}{b}`
- 根号：`\sqrt{x}`
- 求和：`\sum_{i=1}^{n} x_i`
- 积分：`\int_{a}^{b} f(x)dx`
- 矩阵：`\begin{pmatrix} a & b \\ c & d \end{pmatrix}`
- 上标：`x^2`
- 下标：`x_1`
- 希腊字母：`\alpha, \beta, \gamma`

#### 插入MathML公式

1. 点击菜单栏"插入" → "插入 MathML 公式"
2. 或使用快捷键 `Ctrl+M`
3. 在对话框中输入MathML代码
4. 点击"插入"按钮

**常用MathML示例：**
- 分数：`<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>`
- 根号：`<math><msqrt><mi>x</mi></msqrt></math>`
- 上标：`<math><msup><mi>x</mi><mn>2</mn></msup></math>`
- 下标：`<math><msub><mi>x</mi><mn>1</mn></msub></math>`

## 数据存储

### 本地存储

笔记数据使用**SQLite数据库**存储，模仿 macOS 备忘录的存储方式：

```
~/Library/Group Containers/group.com.mathnotes/
├── NoteStore.sqlite        # 笔记数据库
├── sync_config.json       # 同步配置
└── CloudKit/              # CloudKit缓存
    └── *.ckrecord          # CloudKit记录
```

**数据库表结构**：
- `ZNOTE` - 笔记主表
- `ZCKMETADATA` - CloudKit同步元数据

**优势**：
- ✅ 更高的性能和可靠性
- ✅ 支持事务和索引
- ✅ 与 macOS 备忘录相同的存储方式
- ✅ 更好的数据一致性

### iCloud存储

启用iCloud同步后，使用**CloudKit**进行同步（与 macOS 备忘录相同）：

```
~/Library/Group Containers/group.com.mathnotes/CloudKit/
└── *.ckrecord          # CloudKit记录缓存
```

**CloudKit 同步机制**：
- ✅ 使用 CloudKit API，不是 iCloud Drive
- ✅ 增量同步，只传输变更
- ✅ 自动冲突解决
- ✅ 支持推送通知

### 导出文件

导出的文件保存在：
```
~/Documents/MathNotes导出/
```

## 🔄 数据迁移

如果你之前使用的是旧版本（JSON存储），需要迁移数据到新的SQLite数据库：

```bash
python3 migrate_data.py
```

迁移工具会：
1. ✅ 自动检测旧数据
2. ✅ 创建新数据库
3. ✅ 迁移所有笔记
4. ✅ 备份旧数据
5. ✅ 可选删除旧文件

## 快捷键

| 功能 | 快捷键 |
|------|--------|
| 新建笔记 | `Ctrl+N` |
| 新建文件夹 | `Ctrl+Shift+N` |
| 删除笔记 | `Ctrl+D` |
| 插入LaTeX公式 | `Ctrl+L` |
| 插入MathML公式 | `Ctrl+M` |
| 导出为PDF | `Ctrl+Shift+P` |
| 导出为Word | `Ctrl+Shift+W` |
| 导出为Markdown | `Ctrl+Shift+M` |
| 立即同步 | `Ctrl+S` |
| 退出应用 | `Ctrl+Q` |

## 技术栈

- **GUI框架**: PyQt6
- **数学公式渲染**: Matplotlib (LaTeX)
- **MathML解析**: lxml
- **数据存储**: SQLite
- **PDF导出**: QPrinter
- **Word导出**: python-docx
- **Markdown导出**: html2text
- **HTML解析**: BeautifulSoup4
- **云同步**: CloudKit

## 项目结构

```
notes/
├── main.py              # 应用入口
├── main_window.py       # 主窗口
├── note_editor.py       # 笔记编辑器
├── note_manager.py      # 笔记管理器（SQLite）
├── math_renderer.py     # 数学公式渲染器
├── export_manager.py    # 导出管理器
├── icloud_sync.py       # CloudKit同步管理器
├── migrate_data.py      # 数据迁移工具
├── requirements.txt     # 依赖列表
└── README.md           # 说明文档
```

## 常见问题

### Q: LaTeX公式无法渲染？
A: 确保已安装matplotlib库，并且LaTeX语法正确。

### Q: 如何备份笔记？
A: 有三种方式备份笔记：
1. 复制 `~/.mathnotes/notes.json` 文件
2. 使用导出功能导出为PDF、Word或Markdown
3. 启用iCloud同步，自动备份到云端

### Q: 导出Word时提示缺少库？
A: 运行 `pip install python-docx beautifulsoup4` 安装所需库。

### Q: 导出Markdown时提示缺少库？
A: 运行 `pip install html2text beautifulsoup4` 安装所需库。

### Q: iCloud同步不可用？
A: 请确保：
1. 已在系统设置中登录iCloud账户
2. 已启用iCloud Drive
3. 有足够的iCloud存储空间

### Q: 多台设备如何同步？
A: 在每台Mac上都安装应用并启用iCloud同步，笔记会自动在设备间同步。

## 未来计划

- [x] 支持导出为PDF
- [x] 支持导出为Word
- [x] 支持导出为Markdown
- [x] 支持导出为HTML
- [x] 支持iCloud同步
- [ ] 支持图片插入
- [ ] 支持表格插入
- [ ] 支持标签分类
- [ ] 支持全文搜索
- [ ] 支持主题切换
- [ ] 支持版本历史
- [ ] 支持笔记加密

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

---

**享受数学笔记的乐趣！** 📐✨
