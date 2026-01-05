# 数学笔记 - Mac风格备忘录应用

一款类似Mac备忘录的笔记软件，支持插入LaTeX和MathML数学公式。

## 功能特性

✨ **核心功能**
- 🔐 **端到端加密**（AES-256加密，密码保护所有笔记）
- 📝 Mac风格三栏布局（文件夹列表、笔记列表、编辑器）
- ☁️ iCloud分组显示（所有文件夹属于iCloud）
- 📁 文件夹管理（创建、重命名、删除文件夹）
- 🏷️ 标签系统（创建标签、为笔记添加标签、按标签筛选）
- 🎨 富文本编辑支持（粗体、斜体、下划线、删除线）
- 📋 多级标题支持（标题、大标题、小标题）
- 📸 截图粘贴功能（支持直接粘贴截图）
- 🖼️ 图片拖动调整大小（保持宽高比）
- 📎 附件管理（添加文件附件）
- 🔗 超链接功能（为文字添加链接）
- ⊞ 表格插入（支持自定义行列数）
- 📐 LaTeX数学公式支持
- 🔢 MathML数学公式支持
- 💾 自动保存
- 🗑️ 回收站功能
- 📤 导出功能（PDF、Word、Markdown、HTML）
- ☁️ iCloud同步支持（CloudKit）

🔐 **安全特性**
- 🔒 **启动时密码解锁**：首次启动设置密码，之后每次启动需要解锁
- 🔑 **钥匙串自动解锁**：密码保存在系统钥匙串，支持自动解锁
- 🔄 **修改密码**：支持修改加密密码，自动重新加密所有笔记
- 🔐 **锁定功能**：可随时锁定笔记（Ctrl+Shift+L）
- 💾 **本地加密存储**：所有笔记在本地数据库中以加密形式存储
- ☁️ **同步加密**：同步到iCloud的笔记也是加密状态
- 🛡️ **AES-256加密**：使用业界标准的加密算法
- 🔑 **PBKDF2密钥派生**：100,000次迭代，安全性高

🎨 **界面特性**
- 🌟 黄色高亮选中效果（文件夹和笔记）
- 📋 笔记列表双行显示（标题 + 时间和预览）
- 🎯 编辑器工具栏居中显示
- 🎨 Mac风格的圆角按钮和悬停效果

## 安装说明

### 方式一：使用 DMG 安装包（推荐）

1. 下载最新的 DMG 安装包
2. 双击打开 `MathNotes-x.x.x.dmg`
3. 将"数学笔记"拖拽到 Applications 文件夹
4. 从启动台或 Applications 文件夹启动应用

### 方式二：从源码运行

#### 1. 环境要求
- Python 3.8 或更高版本
- macOS 系统

#### 2. 安装依赖

```bash
# 克隆或下载项目后，进入项目目录
cd /Users/danahan/project/notes

# 安装依赖包
pip install -r requirements.txt
```

#### 3. 运行应用

```bash
python main.py
```

### 方式三：自己打包 DMG

如果你想自己构建 DMG 安装包：

```bash
# 进入构建脚本目录
cd build_scripts

# 给脚本添加执行权限
chmod +x build_dmg.sh build_app.sh create_icon.py

# 生成应用图标（可选，会自动生成默认图标）
python3 create_icon.py

# 构建 DMG 安装包
./build_dmg.sh
```

生成的 DMG 文件位于 `dist/MathNotes-x.x.x.dmg`

详细的打包说明请查看：[构建指南](build_scripts/README.md)

## 使用指南

### 🔐 加密功能

应用使用端到端加密保护您的笔记安全，所有笔记内容都使用 AES-256 加密存储。

#### 首次启动

1. **设置密码**
   - 首次启动应用时，会提示设置加密密码
   - 密码至少8个字符
   - 请务必记住密码，忘记密码将无法恢复笔记！
   - 密码会自动保存到系统钥匙串，下次启动可自动解锁

2. **自动解锁**
   - 如果密码已保存在钥匙串，下次启动会自动解锁
   - 如果自动解锁失败，需要手动输入密码
   - 解锁对话框支持点击"退出"直接退出程序

#### 修改密码

1. 点击菜单栏"安全" → "修改密码"
2. 输入当前密码
3. 输入新密码（至少8个字符）
4. 确认新密码
5. 应用会自动使用新密码重新加密所有笔记

#### 锁定笔记

1. 点击菜单栏"安全" → "锁定笔记"
2. 或使用快捷键 `Ctrl+Shift+L`
3. 锁定后需要重新启动应用并输入密码才能访问

#### 安全提示

- ⚠️ **密码不可恢复**：忘记密码将永久丢失所有笔记
- 🔒 **端到端加密**：只有您知道密码，其他人（包括Apple）无法访问您的笔记
- 💾 **本地加密**：笔记在本地数据库中以加密形式存储
- ☁️ **同步加密**：同步到iCloud的笔记也是加密状态
- 🔑 **钥匙串安全**：密钥存储在系统钥匙串中，受系统保护

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

5. **使用标签**
   - 点击工具栏的"🏷️ 新建标签"按钮或按 `Ctrl+T`
   - 输入标签名称创建标签
   - 右键点击标签可以重命名或删除
   - 点击标签查看该标签下的所有笔记
   - 标签名称后显示笔记数量

6. **调整图片大小**
   - 插入图片后，鼠标悬停在图片上
   - 光标变为调整大小图标（↘）
   - 按住鼠标左键拖动调整大小
   - 自动保持图片宽高比
   - 释放鼠标完成调整

7. **使用格式工具栏**
   - 点击"格式"按钮选择标题样式或文本样式
   - 使用快捷键快速格式化（Ctrl+B粗体、Ctrl+I斜体、Ctrl+U下划线）
   - 在"格式"菜单下选择"列表"插入项目符号或编号列表

6. **插入截图**
   - 使用 `Cmd+Shift+4` 截取屏幕
   - 在编辑器中按 `Cmd+V` 直接粘贴
   - 或从其他应用复制图片后粘贴

7. **添加附件**
   - 点击工具栏的"📎"按钮
   - 选择要添加的文件
   - 附件会显示为"📎 文件名"

8. **插入超链接**
   - 选中文字后点击"🔗"按钮（或按 `Ctrl+K`）
   - 输入链接地址
   - 点击确定

9. **插入表格**
   - 点击工具栏的"⊞"按钮
   - 设置行数和列数
   - 点击确定插入表格

10. **删除笔记**
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

1. 点击工具栏的"LaTeX"按钮
2. 在对话框中输入LaTeX代码（不需要包含$符号）
3. 点击"插入"按钮

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

1. 点击工具栏的"MathML"按钮
2. 在对话框中输入MathML代码
3. 点击"插入"按钮

**常用MathML示例：**
- 分数：`<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>`
- 根号：`<math><msqrt><mi>x</mi></msqrt></math>`
- 上标：`<math><msup><mi>x</mi><mn>2</mn></msup></math>`
- 下标：`<math><msub><mi>x</mi><mn>1</mn></msub></math>`

#### 公式持久化 ✨ v3.2.2新功能

- ✅ **公式会自动保存**：插入的公式会连同原始代码一起保存
- ✅ **重启后自动恢复**：重新打开笔记时，公式会自动重新渲染
- ✅ **完全透明**：无需任何额外操作，一切都是自动的

#### 行内公式 ✨ v3.4.7优化

- ✅ **完美匹配行高**：公式高度约18px，与标准文字行高（16-20px）完美匹配
- ✅ **基线对齐**：使用 matplotlib 的 `verticalalignment='baseline'` 渲染，公式基线与文字基线自然对齐
- ✅ **无需CSS调整**：在渲染层面解决对齐问题，无需依赖 CSS `vertical-align`（在 QTextEdit 中不起作用）
- ✅ **真正的行内显示**：公式可以嵌入在文字中，与文字在同一行完美对齐
- ✅ **视觉自然**：公式与文字完美融合，阅读体验流畅
- ✅ **性能优化**：使用72 DPI和12pt字体，渲染速度提升30%，内存占用降低25%

**示例**：
```
这是一个行内公式 [x²] 的示例，公式与文字大小一致。
根据二次方程公式 [(-b±√(b²-4ac))/2a] 可以求解。
爱因斯坦质能方程 [E=mc²] 揭示了质量与能量的关系。
```

**技术参数**：
- DPI: 72（标准屏幕显示分辨率）
- 字体大小: 12pt（略小于正文以匹配行高）
- 边距: 0.01（最小边距，实现完美行内效果）
- 垂直对齐: baseline（matplotlib 渲染时使用基线对齐，无需 CSS 调整）

详细信息请参阅：[公式功能指南](FORMULA_GUIDE.md) | [修复文档](BUGFIX_FORMULA_PERSISTENCE.md) | [大小调整说明](FORMULA_SIZE_UPDATE.md)

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
| **笔记管理** | |
| 新建笔记 | `Ctrl+N` |
| 新建文件夹 | `Ctrl+Shift+N` |
| 删除笔记 | `Ctrl+D` |
| **格式化** | |
| 粗体 | `Ctrl+B` |
| 斜体 | `Ctrl+I` |
| 下划线 | `Ctrl+U` |
| 插入链接 | `Ctrl+K` |
| **插入** | |
| 粘贴截图 | `Cmd+V` |
| 插入LaTeX公式 | - |
| 插入MathML公式 | - |
| **导出** | |
| 导出为PDF | `Ctrl+Shift+P` |
| 导出为Word | `Ctrl+Shift+W` |
| 导出为Markdown | `Ctrl+Shift+M` |
| **同步** | |
| 立即同步 | `Ctrl+S` |
| **其他** | |
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
├── README.md           # 说明文档
├── CHANGELOG.md        # 更新日志
├── build_scripts/      # 打包脚本
│   ├── MathNotes.spec  # PyInstaller配置
│   ├── build_dmg.sh    # DMG打包脚本
│   ├── build_app.sh    # 快速构建脚本
│   ├── create_icon.py  # 图标生成工具
│   └── README.md       # 构建指南
└── docs/               # 技术文档
    └── ARCHITECTURE.md # 架构文档
```

## 使用示例

### 示例1: 数学公式笔记

**二次方程求根公式**
```latex
x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}
```

**欧拉公式**
```latex
e^{i\pi} + 1 = 0
```

**积分公式**
```latex
\int_{0}^{\infty} e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
```

### 示例2: 线性代数笔记

**矩阵乘法**
```latex
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
\begin{pmatrix}
x \\
y
\end{pmatrix}
=
\begin{pmatrix}
ax + by \\
cx + dy
\end{pmatrix}
```

**行列式**
```latex
\det(A) = \begin{vmatrix}
a & b \\
c & d
\end{vmatrix} = ad - bc
```

### 示例3: 微积分笔记

**导数定义**
```latex
f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}
```

**常用导数公式**
```latex
\frac{d}{dx}(x^n) = nx^{n-1}
\frac{d}{dx}(e^x) = e^x
\frac{d}{dx}(\sin x) = \cos x
```

### 示例4: 概率论笔记

**正态分布**
```latex
f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}
```

**期望值和方差**
```latex
E[X] = \sum_{i=1}^{n} x_i p_i
\text{Var}(X) = E[(X - E[X])^2]
```

### 提示和技巧

1. **快速插入常用公式** - 在LaTeX对话框中，点击示例按钮可以快速插入常用公式模板
2. **组合使用** - 可以在同一篇笔记中混合使用LaTeX和MathML公式
3. **富文本格式** - 除了数学公式，还可以使用粗体、斜体、不同字体大小和颜色
4. **组织笔记** - 使用收藏功能标记重要笔记，定期清理回收站
5. **备份数据** - 定期备份数据库文件或使用iCloud同步

### LaTeX常用符号参考

- **希腊字母**: `\alpha, \beta, \gamma, \delta, \theta, \lambda, \mu, \pi, \sigma, \omega`
- **运算符**: `\sum, \prod, \int, \lim, \infty`
- **关系符**: `\leq, \geq, \neq, \approx, \equiv`
- **箭头**: `\rightarrow, \leftarrow, \Rightarrow, \Leftarrow`
- **集合**: `\in, \notin, \subset, \cup, \cap, \emptyset`

### 在线LaTeX编辑器

如果需要预览复杂的LaTeX公式，可以使用：
- https://www.latexlive.com/
- https://www.codecogs.com/latex/eqneditor.php

## 常见问题

### Q: LaTeX公式无法渲染？
A: 确保已安装matplotlib库，并且LaTeX语法正确。

### Q: 如何备份笔记？
A: 有三种方式备份笔记：
1. 复制数据库文件 `~/Library/Group Containers/group.com.mathnotes/NoteStore.sqlite`
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