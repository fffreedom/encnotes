# 附件管理功能说明

## 📎 功能概述

加密笔记应用现已支持附件管理功能，所有附件都会被**加密存储**并支持**iCloud同步**。

## ✨ 主要特性

### 1. 加密存储
- 附件文件会被复制到应用数据目录
- 使用AES-256加密算法加密存储
- 与笔记内容使用相同的加密密钥
- 支持自动去重（相同文件只存储一次）

### 2. 安全管理
- 附件与笔记关联，支持多笔记共享同一附件
- 删除笔记时，如果附件没有其他引用会自动清理
- 临时文件用于打开附件，不会泄露加密内容

### 3. iCloud同步
- 附件存储在iCloud容器目录中
- 自动随笔记同步到其他设备
- 支持跨设备访问加密附件

## 📂 存储位置

```
~/Library/Group Containers/group.com.encnotes/
├── NoteStore.sqlite          # 笔记数据库
├── encryption_config.json    # 加密配置
└── attachments/              # 附件目录
    ├── metadata.json         # 附件元数据
    └── {note_id}/            # 按笔记ID分组
        ├── {uuid}.pdf.enc    # 加密的附件文件
        └── {uuid}.png.enc
```

## 🔧 使用方法

### 插入附件

1. **通过菜单**：
   - 点击菜单栏 `插入` → `插入附件`
   - 或使用快捷键 `Ctrl+Shift+A`

2. **选择文件**：
   - 在文件选择对话框中选择要插入的文件
   - 支持所有文件类型

3. **自动处理**：
   - 文件会被复制到应用目录
   - 自动加密存储
   - 在笔记中插入附件链接

### 打开附件

1. **点击链接**：
   - 直接点击笔记中的附件链接
   - 系统会自动解密并在临时目录打开

2. **安全性**：
   - 临时文件仅在打开时创建
   - 使用系统默认应用打开
   - 原始加密文件保持安全

### 附件显示

附件在笔记中显示为带样式的卡片：

```
📎 文件名.pdf (1.2 MB)
```

- 📎 图标表示这是一个附件
- 显示文件名和大小
- 点击即可打开

## 🔐 加密机制

### 加密流程

1. **添加附件时**：
   ```
   原始文件 → 读取内容 → AES-256加密 → 保存到应用目录
   ```

2. **打开附件时**：
   ```
   加密文件 → AES-256解密 → 写入临时文件 → 系统打开
   ```

### 密钥管理

- 使用与笔记相同的主密钥
- 密钥存储在系统钥匙串中
- 每次启动需要输入密码解锁

## 📊 附件元数据

每个附件都包含以下元数据：

```json
{
  "id": "附件唯一ID",
  "original_name": "原始文件名",
  "encrypted_path": "加密文件路径",
  "file_size": "文件大小（字节）",
  "file_hash": "文件SHA256哈希",
  "note_ids": ["关联的笔记ID列表"],
  "created_at": "创建时间",
  "is_encrypted": true
}
```

## 🔄 同步支持

### iCloud同步

附件目录位于iCloud容器中，会自动同步：

```
~/Library/Group Containers/group.com.encnotes/attachments/
```

### 跨设备访问

1. 在设备A添加附件
2. iCloud自动同步到设备B
3. 在设备B输入密码解锁
4. 可以正常访问所有附件

## 🛠️ 高级功能

### 附件去重

系统会自动检测相同文件（通过SHA256哈希）：

- 相同文件只存储一次
- 多个笔记可以引用同一附件
- 节省存储空间

### 自动清理

删除笔记时：

- 如果附件只被该笔记引用，会自动删除
- 如果附件被其他笔记引用，只移除引用关系
- 可以手动清理孤立附件

### 导出附件

```python
# 通过API导出附件
success, message = attachment_manager.export_attachment(
    attachment_id, 
    export_path
)
```

## 📝 API接口

### AttachmentManager类

```python
# 添加附件
success, message, attachment_id = attachment_manager.add_attachment(
    source_path,  # 源文件路径
    note_id       # 笔记ID
)

# 打开附件
success, message, file_data = attachment_manager.open_attachment(
    attachment_id
)

# 获取附件信息
info = attachment_manager.get_attachment_info(attachment_id)

# 获取笔记的所有附件
attachments = attachment_manager.get_note_attachments(note_id)

# 删除附件
success, message = attachment_manager.delete_attachment(
    attachment_id,
    note_id
)

# 清理孤立附件
count, message = attachment_manager.cleanup_orphaned_attachments()
```

## ⚠️ 注意事项

### 安全性

1. **密码保护**：
   - 必须设置密码才能使用附件功能
   - 密码用于派生加密密钥
   - 忘记密码将无法访问附件

2. **临时文件**：
   - 打开附件时会创建临时文件
   - 启动时自动清理所有临时文件（确保干净状态）
   - 退出时自动清理当前会话的临时文件
   - 详见 `TEMP_FILE_MANAGEMENT.md` 文档

3. **备份**：
   - 定期备份整个数据目录
   - 包括附件和元数据
   - 确保iCloud同步正常

### 性能

1. **大文件**：
   - 支持任意大小的文件
   - 大文件加密/解密需要时间
   - 建议单个附件不超过100MB

2. **存储空间**：
   - 附件会占用本地存储空间
   - iCloud空间也会被占用
   - 注意监控可用空间

### 兼容性

1. **旧版本笔记**：
   - 旧版本使用file://协议的附件仍可访问
   - 新附件使用attachment://协议
   - 建议重新插入旧附件以启用加密

2. **跨平台**：
   - macOS、Windows、Linux都支持
   - 临时文件路径可能不同
   - 打开方式由系统决定

## 🐛 故障排除

### 附件无法打开

1. 检查是否已解锁加密
2. 确认附件文件存在
3. 查看错误日志

### 附件丢失

1. 检查iCloud同步状态
2. 确认metadata.json文件完整
3. 恢复备份

### 同步问题

1. 确认iCloud已登录
2. 检查网络连接
3. 手动触发同步

## 📚 相关文件

- `attachment_manager.py` - 附件管理器核心代码
- `encryption_manager.py` - 加密管理器（新增二进制数据加密）
- `note_editor.py` - 编辑器（附件插入和打开）
- `note_manager.py` - 笔记管理器（集成附件管理器）
- `main_window.py` - 主窗口（传递note_manager）

## 🎯 未来改进

- [ ] 附件预览功能
- [ ] 批量导出附件
- [ ] 附件搜索功能
- [ ] 附件版本管理
- [ ] 压缩大文件
- [ ] 附件统计信息
