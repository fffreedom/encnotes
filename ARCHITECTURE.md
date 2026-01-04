# SQLite + CloudKit 架构说明

## 概述

本应用已升级为使用 **SQLite 数据库** + **CloudKit 同步**，完全模仿 macOS 备忘录的存储和同步机制。

---

## 🗄️ 数据存储架构

### 存储位置

模仿 macOS 备忘录，数据存储在 Group Container 中：

```
~/Library/Group Containers/group.com.mathnotes/
├── NoteStore.sqlite        # 主数据库
├── sync_config.json        # 同步配置
└── CloudKit/               # CloudKit 缓存
    └── *.ckrecord          # CloudKit 记录
```

### 为什么使用 Group Container？

1. **与系统应用一致** - macOS 备忘录也使用这个位置
2. **支持应用扩展** - 未来可以添加 Widget、Today Extension 等
3. **更好的权限管理** - 符合 macOS 沙盒规范
4. **便于备份** - Time Machine 会自动备份

---

## 📊 数据库设计

### 表结构

#### ZNOTE 表（主表）

模仿 Core Data 的命名规范（Z 前缀）：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| Z_PK | INTEGER | 主键（自增） |
| Z_ENT | INTEGER | 实体类型（固定为1） |
| Z_OPT | INTEGER | 乐观锁版本号 |
| ZIDENTIFIER | TEXT | UUID 标识符（唯一） |
| ZTITLE | TEXT | 笔记标题 |
| ZCONTENT | TEXT | 笔记内容（HTML） |
| ZCREATIONDATE | REAL | 创建时间（Cocoa 时间戳） |
| ZMODIFICATIONDATE | REAL | 修改时间（Cocoa 时间戳） |
| ZISFAVORITE | INTEGER | 是否收藏（0/1） |
| ZISDELETED | INTEGER | 是否删除（0/1） |
| ZCKRECORDID | TEXT | CloudKit 记录 ID |
| ZCKRECORDCHANGETAG | TEXT | CloudKit 变更标签 |
| ZCKRECORDSYSTEMFIELDS | BLOB | CloudKit 系统字段 |

#### ZCKMETADATA 表（元数据）

存储 CloudKit 同步元数据：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| Z_PK | INTEGER | 主键 |
| ZKEY | TEXT | 键名（唯一） |
| ZVALUE | TEXT | 值 |

**常用键**：
- `cloudkit_container_id` - CloudKit 容器 ID
- `cloudkit_initialized` - 是否已初始化
- `last_sync_timestamp` - 上次同步时间戳
- `cloudkit_change_token` - 变更令牌

### 索引设计

为提高查询性能，创建了以下索引：

```sql
CREATE INDEX ZIDENTIFIER_INDEX ON ZNOTE(ZIDENTIFIER);
CREATE INDEX ZMODIFICATIONDATE_INDEX ON ZNOTE(ZMODIFICATIONDATE DESC);
CREATE INDEX ZISFAVORITE_INDEX ON ZNOTE(ZISFAVORITE);
CREATE INDEX ZISDELETED_INDEX ON ZNOTE(ZISDELETED);
```

---

## ⏰ 时间戳系统

### Cocoa 时间戳

为了与 macOS 系统保持一致，使用 **Cocoa 时间戳**：

- **定义**：从 2001-01-01 00:00:00 UTC 开始的秒数
- **与 Unix 时间戳的区别**：Unix 从 1970-01-01 开始

### 转换函数

```python
def _timestamp_to_cocoa(dt: datetime) -> float:
    """Python datetime → Cocoa 时间戳"""
    cocoa_epoch = datetime(2001, 1, 1)
    return (dt - cocoa_epoch).total_seconds()

def _cocoa_to_datetime(timestamp: float) -> datetime:
    """Cocoa 时间戳 → Python datetime"""
    cocoa_epoch = datetime(2001, 1, 1)
    return cocoa_epoch + timedelta(seconds=timestamp)
```

### 为什么使用 Cocoa 时间戳？

1. ✅ 与 macOS 备忘录一致
2. ✅ 便于与其他 macOS 应用集成
3. ✅ 符合 Apple 生态系统规范

---

## ☁️ CloudKit 同步架构

### CloudKit vs iCloud Drive

| 特性 | CloudKit | iCloud Drive |
|------|----------|--------------|
| 同步方式 | 增量同步 | 文件同步 |
| 冲突处理 | 自动合并 | 手动处理 |
| 性能 | 高效 | 较慢 |
| 推送通知 | 支持 | 不支持 |
| 使用场景 | 结构化数据 | 文件存储 |

**我们选择 CloudKit**，因为：
- ✅ 与备忘录相同的机制
- ✅ 更高效的同步
- ✅ 更好的冲突处理
- ✅ 支持推送通知

### CloudKit 记录格式

每条笔记在 CloudKit 中存储为一个 Record：

```python
{
    'recordType': 'Note',
    'recordID': 'Note-{UUID}',
    'recordChangeTag': '{SHA256}',
    'fields': {
        'identifier': {'value': '{UUID}'},
        'title': {'value': '笔记标题'},
        'content': {'value': 'HTML内容'},
        'creationDate': {'value': 123456.789},
        'modificationDate': {'value': 123456.789},
        'isFavorite': {'value': False},
        'isDeleted': {'value': False}
    }
}
```

### 同步流程

#### 1. 推送（Push）

```
本地修改 → 检测变更 → 创建 CKRecord → 上传到 CloudKit → 更新元数据
```

**实现**：
```python
def sync_notes(self) -> Tuple[bool, str]:
    # 1. 获取上次同步时间
    last_sync = get_sync_metadata('last_sync_timestamp')
    
    # 2. 查询修改的笔记
    modified_notes = get_notes_modified_after(last_sync)
    
    # 3. 推送到 CloudKit
    synced_count = _push_to_cloudkit(modified_notes)
    
    # 4. 更新同步时间
    set_sync_metadata('last_sync_timestamp', now())
    
    return True, f"同步成功，已上传{synced_count}条笔记"
```

#### 2. 拉取（Pull）

```
CloudKit → 获取变更 → 比较时间戳 → 合并数据 → 更新本地数据库
```

**实现**：
```python
def pull_notes(self) -> Tuple[bool, any]:
    # 1. 从 CloudKit 读取记录
    remote_records = _fetch_from_cloudkit()
    
    # 2. 返回记录列表
    return True, {'notes': remote_records, 'count': len(remote_records)}

def merge_notes(self, remote_records: List[Dict]) -> int:
    # 对每条远程记录
    for ck_record in remote_records:
        note_id = ck_record['fields']['identifier']['value']
        local_note = get_note(note_id)
        
        if not local_note:
            # 本地不存在，创建
            create_note(...)
        else:
            # 比较修改时间
            if remote_modified > local_modified:
                # 远程更新，更新本地
                update_note(...)
        
        # 更新 CloudKit 元数据
        update_cloudkit_metadata(...)
```

#### 3. 冲突处理

**策略**：Last Write Wins（最后写入获胜）

```python
# 比较修改时间
remote_modified = ck_record['fields']['modificationDate']['value']
local_modified = local_note['_cocoa_modified']

if remote_modified > local_modified:
    # 使用远程版本
    update_local_from_remote()
else:
    # 保留本地版本
    keep_local_version()
```

### 变更追踪

使用 **Change Token** 实现增量同步：

```python
# 保存变更令牌
set_sync_metadata('cloudkit_change_token', token)

# 下次同步时使用令牌
change_token = get_sync_metadata('cloudkit_change_token')
fetch_changes_since(change_token)
```

---

## 🔄 数据迁移

### 从 JSON 迁移到 SQLite

提供自动迁移工具 `migrate_data.py`：

```bash
python3 migrate_data.py
```

**迁移步骤**：

1. **检测旧数据**
   ```python
   old_notes_file = Path.home() / ".mathnotes" / "notes.json"
   if old_notes_file.exists():
       # 读取旧数据
   ```

2. **创建新数据库**
   ```python
   note_manager = NoteManager()  # 自动创建 SQLite 数据库
   ```

3. **转换并插入**
   ```python
   for note_id, note_data in old_notes.items():
       # 转换时间格式
       created_cocoa = _timestamp_to_cocoa(created_at)
       
       # 插入数据库
       cursor.execute('''
           INSERT INTO ZNOTE (...)
           VALUES (?, ?, ?, ...)
       ''', (...))
   ```

4. **备份旧数据**
   ```python
   backup_file = f"notes_backup_{timestamp}.json"
   shutil.copy2(old_notes_file, backup_file)
   ```

---

## 🔧 API 设计

### NoteManager（数据库管理）

```python
class NoteManager:
    def __init__(self):
        """初始化数据库连接"""
        
    def create_note(title, content) -> str:
        """创建笔记，返回 UUID"""
        
    def get_note(note_id) -> Dict:
        """获取笔记"""
        
    def update_note(note_id, title, content):
        """更新笔记"""
        
    def delete_note(note_id):
        """软删除（移到回收站）"""
        
    def permanently_delete_note(note_id):
        """永久删除"""
        
    def get_all_notes() -> List[Dict]:
        """获取所有笔记"""
        
    def get_notes_modified_after(timestamp) -> List[Dict]:
        """获取指定时间后修改的笔记（用于同步）"""
        
    def update_cloudkit_metadata(note_id, record_id, change_tag):
        """更新 CloudKit 元数据"""
        
    def get_sync_metadata(key) -> str:
        """获取同步元数据"""
        
    def set_sync_metadata(key, value):
        """设置同步元数据"""
```

### CloudKitSyncManager（同步管理）

```python
class CloudKitSyncManager:
    def __init__(self, note_manager):
        """初始化同步管理器"""
        
    def enable_sync() -> Tuple[bool, str]:
        """启用同步"""
        
    def disable_sync() -> Tuple[bool, str]:
        """禁用同步"""
        
    def sync_notes() -> Tuple[bool, str]:
        """推送笔记到 CloudKit"""
        
    def pull_notes() -> Tuple[bool, any]:
        """从 CloudKit 拉取笔记"""
        
    def merge_notes(remote_records) -> int:
        """合并远程笔记"""
        
    def auto_sync() -> Tuple[bool, str]:
        """自动同步"""
        
    def fetch_changes() -> Tuple[bool, str]:
        """获取 CloudKit 变更"""
        
    def get_sync_status() -> Dict:
        """获取同步状态"""
```

---

## 🎯 性能优化

### 数据库优化

1. **索引优化**
   - 为常用查询字段创建索引
   - 使用复合索引提高多条件查询性能

2. **连接池**
   - 使用单例模式管理数据库连接
   - 避免频繁打开关闭连接

3. **事务处理**
   - 批量操作使用事务
   - 减少磁盘 I/O

### 同步优化

1. **增量同步**
   - 只同步修改的笔记
   - 使用时间戳过滤

2. **批量操作**
   - 批量上传/下载记录
   - 减少网络请求次数

3. **后台同步**
   - 使用定时器自动同步
   - 不阻塞 UI 操作

---

## 🔒 数据安全

### 本地安全

1. **数据库加密**（可选）
   - 使用 SQLCipher 加密数据库
   - 保护敏感信息

2. **权限控制**
   - 使用 macOS 沙盒机制
   - 限制文件访问权限

### 云端安全

1. **CloudKit 加密**
   - 数据传输使用 HTTPS
   - 存储在 iCloud 中加密

2. **身份验证**
   - 使用 iCloud 账户认证
   - 只有授权设备可访问

---

## 📈 未来扩展

### 计划中的功能

1. **推送通知**
   - 使用 CloudKit 订阅
   - 远程修改时实时通知

2. **协作编辑**
   - 使用 CloudKit 共享
   - 多人协作编辑笔记

3. **版本历史**
   - 记录笔记修改历史
   - 支持回滚到历史版本

4. **全文搜索**
   - 使用 SQLite FTS5
   - 支持中文分词

5. **应用扩展**
   - Today Widget
   - Share Extension
   - Siri Shortcuts

---

## 🐛 故障排查

### 常见问题

#### 1. 数据库锁定

**问题**：`database is locked`

**解决**：
```python
# 使用 WAL 模式
conn.execute('PRAGMA journal_mode=WAL')
```

#### 2. 同步失败

**问题**：CloudKit 同步失败

**检查**：
- iCloud 账户是否登录
- 网络连接是否正常
- CloudKit 容器是否正确配置

#### 3. 数据迁移失败

**问题**：从 JSON 迁移失败

**解决**：
- 检查旧数据格式
- 手动备份数据
- 逐条迁移并记录错误

---

## 📚 参考资料

- [SQLite 官方文档](https://www.sqlite.org/docs.html)
- [CloudKit 开发指南](https://developer.apple.com/documentation/cloudkit)
- [Core Data 编程指南](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/CoreData/)
- [macOS 沙盒指南](https://developer.apple.com/library/archive/documentation/Security/Conceptual/AppSandboxDesignGuide/)

---

**架构设计完成！** 🎉
