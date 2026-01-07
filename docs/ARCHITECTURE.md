# 架构文档

## 概述

加密笔记应用是一款模仿 macOS 备忘录的笔记软件，采用 Python + PyQt6 开发，支持富文本编辑和数学公式渲染。本文档详细说明应用的技术架构、设计理念和实现细节。

## 设计理念

### 1. 模仿 macOS 备忘录

应用在多个层面模仿 macOS 备忘录的设计：

- **UI布局**: 三栏式布局（文件夹列表、笔记列表、编辑器）
- **数据存储**: 使用 SQLite 数据库，存储在 `~/Library/Group Containers/` 目录
- **同步机制**: 使用 CloudKit API 进行 iCloud 同步
- **用户体验**: 自动保存、即时搜索、流畅的交互

### 2. 核心原则

- **简洁性**: 界面简洁，功能直观
- **性能**: 快速响应，流畅体验
- **可靠性**: 数据安全，自动备份
- **扩展性**: 模块化设计，易于扩展

## 技术架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                      用户界面层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  MainWindow  │  │  NoteEditor  │  │  Dialogs     │  │
│  │  (主窗口)    │  │  (编辑器)    │  │  (对话框)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                      业务逻辑层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ NoteManager  │  │MathRenderer  │  │ExportManager │  │
│  │ (笔记管理)   │  │(公式渲染)    │  │(导出管理)    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                      数据访问层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   SQLite     │  │  CloudKit    │  │  FileSystem  │  │
│  │  (本地存储)  │  │  (云同步)    │  │  (文件导出)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 核心模块

#### 1. 主窗口模块 (main_window.py)

**职责**:
- 管理应用的主界面
- 协调各个子模块
- 处理用户交互事件

**关键组件**:
- `MainWindow`: 主窗口类，继承自 `QMainWindow`
- 三栏布局: 文件夹列表、笔记列表、编辑器
- 工具栏: 新建、删除、导出、同步等功能按钮
- 菜单栏: 文件、编辑、插入、格式、同步等菜单

**设计模式**:
- MVC模式: MainWindow 作为 Controller，协调 Model (NoteManager) 和 View (NoteEditor)
- 观察者模式: 监听编辑器的文本变化，自动保存

#### 2. 笔记编辑器模块 (note_editor.py)

**职责**:
- 提供富文本编辑功能
- 支持数学公式插入
- 支持图片、附件、超链接、表格

**关键组件**:
- `NoteEditor`: 编辑器类，包含 `QTextEdit` 和格式工具栏
- 格式工具栏: 标题、粗体、斜体、下划线、列表等
- 插入工具栏: 截图、附件、链接、表格、公式

**技术实现**:
- 使用 `QTextEdit` 作为编辑器核心
- 使用 `QTextCharFormat` 和 `QTextBlockFormat` 实现富文本格式
- 使用 `QTextCursor` 操作文本内容
- 图片以 base64 编码嵌入 HTML
- 公式以图片形式插入，元数据保存在 `alt` 属性

**公式持久化机制**:
```python
# 公式元数据格式: MATH:type:code
# 例如: MATH:latex:x^2+y^2=r^2
alt_text = f"MATH:{formula_type}:{formula_code}"
```

#### 3. 笔记管理器模块 (note_manager.py)

**职责**:
- 管理笔记的 CRUD 操作
- 管理文件夹的 CRUD 操作
- 提供搜索和过滤功能

**数据库设计**:

```sql
-- 笔记表
CREATE TABLE ZNOTE (
    Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
    ZTITLE TEXT,
    ZCONTENT TEXT,
    ZCREATIONDATE REAL,
    ZMODIFICATIONDATE REAL,
    ZFOLDER INTEGER,
    ZISFAVORITE INTEGER DEFAULT 0,
    ZISTRASHED INTEGER DEFAULT 0
);

-- 文件夹表
CREATE TABLE ZFOLDER (
    Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
    ZNAME TEXT NOT NULL,
    ZCREATIONDATE REAL,
    ZMODIFICATIONDATE REAL
);

-- CloudKit 元数据表
CREATE TABLE ZCKMETADATA (
    Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
    ZRECORDID TEXT UNIQUE,
    ZRECORDTYPE TEXT,
    ZLOCALID INTEGER,
    ZMODIFICATIONDATE REAL,
    ZCHANGETAG TEXT
);

-- 索引
CREATE INDEX idx_note_folder ON ZNOTE(ZFOLDER);
CREATE INDEX idx_note_favorite ON ZNOTE(ZISFAVORITE);
CREATE INDEX idx_note_trashed ON ZNOTE(ZISTRASHED);
CREATE INDEX idx_note_modification ON ZNOTE(ZMODIFICATIONDATE);
```

**关键方法**:
- `create_note()`: 创建新笔记
- `update_note()`: 更新笔记内容
- `delete_note()`: 删除笔记（移到回收站）
- `get_all_notes()`: 获取所有笔记
- `search_notes()`: 搜索笔记
- `create_folder()`: 创建文件夹
- `get_folders()`: 获取所有文件夹

#### 4. 数学公式渲染器模块 (math_renderer.py)

**职责**:
- 渲染 LaTeX 公式
- 渲染 MathML 公式
- 缓存渲染结果

**技术实现**:

**LaTeX 渲染**:
```python
def render_latex(latex_code):
    fig, ax = plt.subplots(figsize=(0.1, 0.1))
    ax.text(0.5, 0.5, f'${latex_code}$', 
            fontsize=14, ha='center', va='center')
    ax.axis('off')
    
    # 保存为PNG
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, 
                bbox_inches='tight', pad_inches=0.05,
                transparent=True)
    return buf.getvalue()
```

**MathML 渲染**:
- 使用 `lxml` 解析 MathML
- 转换为 LaTeX 代码
- 使用 LaTeX 渲染器渲染

**性能优化**:
- 公式缓存: 相同公式只渲染一次
- 异步渲染: 避免阻塞 UI 线程
- 图片压缩: 减小内存占用

**渲染参数**:
- DPI: 100 (与文字大小匹配)
- 字体大小: 14pt (与正文一致)
- 透明背景: 支持
- 边距: 0.05 inches

#### 5. 导出管理器模块 (export_manager.py)

**职责**:
- 导出笔记为 PDF
- 导出笔记为 Word
- 导出笔记为 Markdown
- 导出笔记为 HTML

**技术实现**:

**PDF 导出**:
```python
def export_to_pdf(note, filepath):
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(filepath)
    
    document = QTextDocument()
    document.setHtml(note['content'])
    document.print_(printer)
```

**Word 导出**:
```python
def export_to_word(note, filepath):
    doc = Document()
    doc.add_heading(note['title'], 0)
    
    # 解析HTML并转换为Word格式
    soup = BeautifulSoup(note['content'], 'html.parser')
    for element in soup.descendants:
        if element.name == 'p':
            doc.add_paragraph(element.get_text())
        elif element.name == 'img':
            # 处理图片
            pass
    
    doc.save(filepath)
```

**Markdown 导出**:
```python
def export_to_markdown(note, filepath):
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    markdown_content = h.handle(note['content'])
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# {note['title']}\n\n")
        f.write(markdown_content)
```

#### 6. iCloud 同步模块 (icloud_sync.py)

**职责**:
- 使用 CloudKit API 同步笔记
- 处理冲突解决
- 管理同步状态

**同步机制**:

**增量同步**:
```python
def sync():
    # 1. 获取本地变更
    local_changes = get_local_changes()
    
    # 2. 推送到 CloudKit
    for change in local_changes:
        push_to_cloudkit(change)
    
    # 3. 从 CloudKit 拉取变更
    remote_changes = fetch_from_cloudkit()
    
    # 4. 合并变更
    for change in remote_changes:
        merge_change(change)
```

**冲突解决策略**:
- 最后修改时间优先: 保留最新的版本
- 自动合并: 对于不冲突的字段自动合并
- 用户选择: 对于严重冲突，提示用户选择

**CloudKit 记录格式**:
```json
{
  "recordType": "Note",
  "recordID": "uuid",
  "fields": {
    "title": "笔记标题",
    "content": "笔记内容",
    "modificationDate": 1234567890,
    "folder": "文件夹ID",
    "isFavorite": false,
    "isTrashed": false
  }
}
```

## 数据流

### 1. 创建笔记流程

```
用户点击"新建笔记"
    ↓
MainWindow.create_note()
    ↓
NoteManager.create_note()
    ↓
插入数据到 SQLite
    ↓
返回笔记ID
    ↓
MainWindow 刷新笔记列表
    ↓
选中新笔记
    ↓
NoteEditor 显示空白编辑器
```

### 2. 编辑笔记流程

```
用户在编辑器中输入
    ↓
NoteEditor.textChanged 信号
    ↓
MainWindow.on_text_changed()
    ↓
启动自动保存定时器 (2秒)
    ↓
定时器触发
    ↓
NoteManager.update_note()
    ↓
更新 SQLite 数据库
    ↓
更新笔记列表显示
```

### 3. 插入公式流程

```
用户点击"插入公式"
    ↓
显示公式输入对话框
    ↓
用户输入 LaTeX/MathML 代码
    ↓
MathRenderer.render()
    ↓
生成 PNG 图片
    ↓
转换为 base64
    ↓
创建 <img> 标签
    ↓
设置 alt 属性 (MATH:type:code)
    ↓
插入到编辑器
    ↓
触发自动保存
```

### 4. 同步流程

```
用户点击"立即同步"
    ↓
ICloudSync.sync()
    ↓
获取本地变更
    ↓
推送到 CloudKit
    ↓
从 CloudKit 拉取变更
    ↓
检测冲突
    ↓
解决冲突
    ↓
更新本地数据库
    ↓
刷新界面
    ↓
显示同步结果
```

## 性能优化

### 1. 数据库优化

- **索引**: 为常用查询字段创建索引
- **事务**: 批量操作使用事务
- **连接池**: 复用数据库连接
- **查询优化**: 使用 LIMIT 和 OFFSET 分页加载

### 2. UI 优化

- **虚拟滚动**: 笔记列表使用虚拟滚动，只渲染可见项
- **延迟加载**: 编辑器内容延迟加载
- **防抖**: 搜索和自动保存使用防抖
- **异步操作**: 耗时操作使用 QThread

### 3. 公式渲染优化

- **缓存**: 相同公式只渲染一次
- **预渲染**: 预先渲染常用公式
- **压缩**: 压缩图片减小内存占用
- **异步**: 异步渲染避免阻塞 UI

### 4. 同步优化

- **增量同步**: 只同步变更的数据
- **批量操作**: 批量推送和拉取
- **压缩**: 压缩传输数据
- **后台同步**: 使用后台线程同步

## 安全性

### 1. 数据安全

- **本地加密**: SQLite 数据库可选加密
- **传输加密**: CloudKit 使用 HTTPS
- **备份**: 自动备份到 iCloud
- **版本控制**: 保留历史版本

### 2. 隐私保护

- **本地优先**: 数据优先存储在本地
- **用户控制**: 用户可选择是否启用同步
- **数据隔离**: 每个用户的数据完全隔离
- **透明性**: 明确告知数据存储位置

## 扩展性

### 1. 插件系统

未来可以添加插件系统，支持：
- 自定义公式渲染器
- 自定义导出格式
- 自定义主题
- 自定义快捷键

### 2. 多平台支持

当前仅支持 macOS，未来可以扩展到：
- Windows
- Linux
- iOS (使用 PyQt for iOS)
- Web (使用 PyScript)

### 3. 协作功能

未来可以添加协作功能：
- 多人编辑
- 评论和批注
- 版本对比
- 权限管理

## 测试策略

### 1. 单元测试

- 测试每个模块的核心功能
- 使用 pytest 框架
- 覆盖率目标: 80%

### 2. 集成测试

- 测试模块间的交互
- 测试数据流
- 测试同步机制

### 3. UI 测试

- 使用 PyQt Test 框架
- 测试用户交互
- 测试界面响应

### 4. 性能测试

- 测试大量笔记的性能
- 测试公式渲染性能
- 测试同步性能

## 部署

### 1. 打包

使用 PyInstaller 打包为独立应用：

```bash
pyinstaller --name="加密笔记" \
            --windowed \
            --icon=icon.icns \
            --add-data="resources:resources" \
            main.py
```

### 2. 分发

- **Mac App Store**: 提交到 Mac App Store
- **直接下载**: 提供 DMG 文件下载
- **Homebrew**: 添加到 Homebrew Cask

### 3. 更新

- **自动更新**: 检测新版本并提示更新
- **增量更新**: 只下载变更的文件
- **回滚**: 支持回滚到旧版本

## 未来规划

### 短期 (1-3个月)

- [ ] 添加图片插入功能
- [ ] 添加表格编辑功能
- [ ] 添加标签分类功能
- [ ] 添加全文搜索功能

### 中期 (3-6个月)

- [ ] 添加主题切换功能
- [ ] 添加版本历史功能
- [ ] 添加笔记加密功能
- [ ] 优化性能

### 长期 (6-12个月)

- [ ] 支持 Windows 和 Linux
- [ ] 添加协作功能
- [ ] 添加插件系统
- [ ] 开发移动端应用

## 参考资料

- [PyQt6 官方文档](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [SQLite 官方文档](https://www.sqlite.org/docs.html)
- [CloudKit 官方文档](https://developer.apple.com/documentation/cloudkit)
- [Matplotlib 官方文档](https://matplotlib.org/stable/contents.html)
- [LaTeX 数学符号](https://www.overleaf.com/learn/latex/List_of_Greek_letters_and_math_symbols)

---

**文档版本**: v1.0  
**最后更新**: 2026-01-05  
**维护者**: 开发团队
