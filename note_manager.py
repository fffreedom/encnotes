#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
笔记管理器 - 使用SQLite数据库存储笔记
"""

import os
import sqlite3
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from encryption_manager import EncryptionManager
from attachment_manager import AttachmentManager

logger = logging.getLogger(__name__)


class NoteManager:
    """笔记管理器类 - 使用SQLite数据库"""
    
    def __init__(self):
        # 数据存储路径 - 模仿macOS备忘录的存储位置
        _test_dir = os.environ.get("ENCNOTES_TEST_DATA_DIR")
        if _test_dir:
            self.data_dir = Path(_test_dir)
        else:
            self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / "NoteStore.sqlite"
        self.conn = None
        
        # 初始化加密管理器
        self.encryption_manager = EncryptionManager()
        
        # 初始化附件管理器
        self.attachment_manager = AttachmentManager(self.encryption_manager)
        
        self.init_database()
        
    def _migrate_table_names(self, cursor):
        """一次性迁移：将旧的Z前缀表名重命名为enc_前缀小写表名。

        在数据库中检测到旧表名时自动触发：先备份数据库文件，再使用
        ALTER TABLE ... RENAME TO 重命名所有表，最后删除旧的索引
        （init_database 后续会用新名称重建索引）。
        """
        renames = [
            ('ZFOLDER',     'enc_folder'),
            ('ZNOTE',       'enc_note'),
            ('ZTAG',        'enc_tag'),
            ('ZNOTETAG',    'enc_note_tag'),
            ('ZCKMETADATA', 'enc_ck_metadata'),
            ('ZAPPSTATE',   'enc_app_state'),
        ]
        existing = {row[0] for row in
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()}
        needs_migration = any(old in existing for old, _ in renames)

        if not needs_migration:
            return

        # 迁移前先备份数据库文件
        import shutil
        backup = self.db_path.parent / (
            f"NoteStore.sqlite.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(self.db_path, backup)
        logger.info("数据库备份已创建: %s", backup)

        # 逐一重命名旧表
        for old_name, new_name in renames:
            if old_name in existing and new_name not in existing:
                cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')
                logger.info("表重命名: %s -> %s", old_name, new_name)

        # 删除旧的Z前缀索引（init_database 会用新名称重建）
        old_indexes = [
            'ZIDENTIFIER_INDEX', 'ZMODIFICATIONDATE_INDEX', 'ZISFAVORITE_INDEX',
            'ZISDELETED_INDEX', 'ZFOLDERID_INDEX', 'ZFOLDER_IDENTIFIER_INDEX',
            'ZFOLDER_ORDERINDEX_INDEX', 'ZTAG_IDENTIFIER_INDEX',
            'ZNOTETAG_NOTEID_INDEX', 'ZNOTETAG_TAGID_INDEX',
        ]
        for idx in old_indexes:
            cursor.execute(f'DROP INDEX IF EXISTS "{idx}"')

        self.conn.commit()
        logger.info("数据库表名迁移完成")

    def _migrate_column_names(self, cursor):
        """一次性迁移：将Z前缀列名重命名为enc_前缀小写列名。

        检测到 enc_note 表中存在旧列名 ZIDENTIFIER 时触发迁移：先备份数据库
        文件，然后对所有6张表逐列执行 ALTER TABLE … RENAME COLUMN。
        """
        cursor.execute("PRAGMA table_info(enc_note)")
        cols = {row[1] for row in cursor.fetchall()}
        if 'ZIDENTIFIER' not in cols:
            return  # 已迁移或全新数据库，跳过

        # 迁移前先备份
        import shutil
        backup = self.db_path.parent / (
            f"NoteStore.sqlite.colbak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        shutil.copy2(self.db_path, backup)
        logger.info("列迁移前备份: %s", backup)

        renames = {
            'enc_note': [
                ('Z_PK', 'enc_pk'), ('Z_ENT', 'enc_ent'), ('Z_OPT', 'enc_opt'),
                ('ZIDENTIFIER', 'enc_identifier'), ('ZFOLDERID', 'enc_folder_id'),
                ('ZTITLE', 'enc_title'), ('ZCONTENT', 'enc_content'),
                ('ZCREATIONDATE', 'enc_created_at'), ('ZMODIFICATIONDATE', 'enc_modified_at'),
                ('ZISFAVORITE', 'enc_is_favorite'), ('ZISDELETED', 'enc_is_deleted'),
                ('ZISPINNED', 'enc_is_pinned'), ('ZCURSORPOSITION', 'enc_cursor_position'),
                ('ZCKRECORDID', 'enc_ck_record_id'), ('ZCKRECORDCHANGETAG', 'enc_ck_change_tag'),
                ('ZCKRECORDSYSTEMFIELDS', 'enc_ck_system_fields'),
            ],
            'enc_folder': [
                ('Z_PK', 'enc_pk'), ('Z_ENT', 'enc_ent'), ('Z_OPT', 'enc_opt'),
                ('ZIDENTIFIER', 'enc_identifier'), ('ZNAME', 'enc_name'),
                ('ZPARENTFOLDERID', 'enc_parent_folder_id'),
                ('ZCREATIONDATE', 'enc_created_at'), ('ZMODIFICATIONDATE', 'enc_modified_at'),
                ('ZORDERINDEX', 'enc_order_index'), ('ZLASTNOTEID', 'enc_last_note_id'),
            ],
            'enc_tag': [
                ('Z_PK', 'enc_pk'), ('Z_ENT', 'enc_ent'), ('Z_OPT', 'enc_opt'),
                ('ZIDENTIFIER', 'enc_identifier'), ('ZNAME', 'enc_name'),
                ('ZCREATIONDATE', 'enc_created_at'), ('ZMODIFICATIONDATE', 'enc_modified_at'),
            ],
            'enc_note_tag': [
                ('Z_PK', 'enc_pk'), ('ZNOTEID', 'enc_note_id'), ('ZTAGID', 'enc_tag_id'),
            ],
            'enc_ck_metadata': [
                ('Z_PK', 'enc_pk'), ('ZKEY', 'enc_key'), ('ZVALUE', 'enc_value'),
            ],
            'enc_app_state': [
                ('Z_PK', 'enc_pk'), ('ZKEY', 'enc_key'), ('ZVALUE', 'enc_value'),
                ('ZMODIFICATIONDATE', 'enc_modified_at'),
            ],
        }
        for table, pairs in renames.items():
            # Only rename columns that actually exist (handles partial migrations)
            cursor.execute(f"PRAGMA table_info({table})")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for old_col, new_col in pairs:
                if old_col in existing_cols:
                    cursor.execute(
                        f'ALTER TABLE "{table}" RENAME COLUMN "{old_col}" TO "{new_col}"'
                    )
                    logger.info("列重命名: %s.%s -> %s", table, old_col, new_col)

        self.conn.commit()
        logger.info("数据库列名迁移完成")

    def init_database(self):
        """初始化数据库，创建表结构"""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问

        cursor = self.conn.cursor()

        # 迁移旧的Z前缀表名（历史数据库一次性操作）
        self._migrate_table_names(cursor)

        # 迁移旧的Z前缀列名（历史数据库一次性操作）
        self._migrate_column_names(cursor)

        # 创建文件夹表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_folder (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_ent INTEGER DEFAULT 2,
                enc_opt INTEGER DEFAULT 1,
                enc_identifier TEXT UNIQUE NOT NULL,
                enc_name TEXT NOT NULL,
                enc_parent_folder_id TEXT,
                enc_created_at REAL,
                enc_modified_at REAL,
                enc_order_index INTEGER DEFAULT 0,
                FOREIGN KEY (enc_parent_folder_id) REFERENCES enc_folder(enc_identifier)
            )
        ''')

        # 创建笔记表 - 模仿备忘录的表结构
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_note (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_ent INTEGER DEFAULT 1,
                enc_opt INTEGER DEFAULT 1,
                enc_identifier TEXT UNIQUE NOT NULL,
                enc_folder_id TEXT,
                enc_title TEXT,
                enc_content TEXT,
                enc_created_at REAL,
                enc_modified_at REAL,
                enc_is_favorite INTEGER DEFAULT 0,
                enc_is_deleted INTEGER DEFAULT 0,
                enc_is_pinned INTEGER DEFAULT 0,
                enc_cursor_position INTEGER DEFAULT 0,
                enc_ck_record_id TEXT,
                enc_ck_change_tag TEXT,
                enc_ck_system_fields BLOB,
                FOREIGN KEY (enc_folder_id) REFERENCES enc_folder(enc_identifier)
            )
        ''')

        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_identifier_idx
            ON enc_note(enc_identifier)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_moddate_idx
            ON enc_note(enc_modified_at DESC)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_favorite_idx
            ON enc_note(enc_is_favorite)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_deleted_idx
            ON enc_note(enc_is_deleted)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_folderid_idx
            ON enc_note(enc_folder_id)
        ''')

        # 创建文件夹索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_folder_identifier_idx
            ON enc_folder(enc_identifier)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_folder_orderindex_idx
            ON enc_folder(enc_order_index)
        ''')

        # 创建CloudKit同步元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_ck_metadata (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_key TEXT UNIQUE NOT NULL,
                enc_value TEXT
            )
        ''')

        # 创建应用状态表（用于替代QSettings）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_app_state (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_key TEXT UNIQUE NOT NULL,
                enc_value TEXT,
                enc_modified_at REAL
            )
        ''')

        # 创建标签表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_tag (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_ent INTEGER DEFAULT 3,
                enc_opt INTEGER DEFAULT 1,
                enc_identifier TEXT UNIQUE NOT NULL,
                enc_name TEXT NOT NULL,
                enc_created_at REAL,
                enc_modified_at REAL
            )
        ''')

        # 创建笔记-标签关联表（多对多关系）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS enc_note_tag (
                enc_pk INTEGER PRIMARY KEY AUTOINCREMENT,
                enc_note_id TEXT NOT NULL,
                enc_tag_id TEXT NOT NULL,
                FOREIGN KEY (enc_note_id) REFERENCES enc_note(enc_identifier),
                FOREIGN KEY (enc_tag_id) REFERENCES enc_tag(enc_identifier),
                UNIQUE(enc_note_id, enc_tag_id)
            )
        ''')

        # 创建标签索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_tag_identifier_idx
            ON enc_tag(enc_identifier)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_tag_noteid_idx
            ON enc_note_tag(enc_note_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS enc_note_tag_tagid_idx
            ON enc_note_tag(enc_tag_id)
        ''')

        # 数据库迁移：为现有数据库添加enc_parent_folder_id字段
        try:
            # 检查enc_folder表是否已有enc_parent_folder_id字段
            cursor.execute("PRAGMA table_info(enc_folder)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'enc_parent_folder_id' not in columns:
                # 添加enc_parent_folder_id字段
                cursor.execute('''
                    ALTER TABLE enc_folder ADD COLUMN enc_parent_folder_id TEXT
                ''')
                print("数据库迁移：已添加enc_parent_folder_id字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")

        # 数据库迁移：为现有数据库添加enc_is_pinned字段
        try:
            # 检查enc_note表是否已有enc_is_pinned字段
            cursor.execute("PRAGMA table_info(enc_note)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'enc_is_pinned' not in columns:
                # 添加enc_is_pinned字段
                cursor.execute('''
                    ALTER TABLE enc_note ADD COLUMN enc_is_pinned INTEGER DEFAULT 0
                ''')
                print("数据库迁移：已添加enc_is_pinned字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")

        # 数据库迁移：为现有数据库添加enc_cursor_position字段
        try:
            # 检查enc_note表是否已有enc_cursor_position字段
            cursor.execute("PRAGMA table_info(enc_note)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'enc_cursor_position' not in columns:
                # 添加enc_cursor_position字段
                cursor.execute('''
                    ALTER TABLE enc_note ADD COLUMN enc_cursor_position INTEGER DEFAULT 0
                ''')
                print("数据库迁移：已添加enc_cursor_position字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")

        # 数据库迁移：为现有数据库添加enc_last_note_id字段
        try:
            # 检查enc_folder表是否已有enc_last_note_id字段
            cursor.execute("PRAGMA table_info(enc_folder)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'enc_last_note_id' not in columns:
                # 添加enc_last_note_id字段
                cursor.execute('''
                    ALTER TABLE enc_folder ADD COLUMN enc_last_note_id TEXT
                ''')
                print("数据库迁移：已添加enc_last_note_id字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")

        self.conn.commit()
        
    def _timestamp_to_cocoa(self, dt: datetime) -> float:
        """
        将Python datetime转换为Cocoa时间戳
        Cocoa时间戳是从2001-01-01 00:00:00 UTC开始的秒数
        """
        cocoa_epoch = datetime(2001, 1, 1)
        return (dt - cocoa_epoch).total_seconds()
        
    def _cocoa_to_datetime(self, timestamp: float) -> datetime:
        """将Cocoa时间戳转换为Python datetime"""
        cocoa_epoch = datetime(2001, 1, 1)
        from datetime import timedelta
        return cocoa_epoch + timedelta(seconds=timestamp)
        
    def create_note(self, title: str = "无标题", content: str = "", folder_id: Optional[str] = None) -> str:
        """创建新笔记"""
        note_id = str(uuid.uuid4())
        now = datetime.now()
        cocoa_time = self._timestamp_to_cocoa(now)
        
        # 加密内容
        encrypted_content = self._encrypt_content(content)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO enc_note (
                enc_identifier, enc_folder_id, enc_title, enc_content, 
                enc_created_at, enc_modified_at,
                enc_is_favorite, enc_is_deleted
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        ''', (note_id, folder_id, title, encrypted_content, cocoa_time, cocoa_time))
        
        self.conn.commit()
        return note_id
        
    def get_note(self, note_id: str) -> Optional[Dict]:
        """获取笔记"""
        import traceback
        # logger.debug(f"[get_note] 调用堆栈:\n{''.join(traceback.format_stack()[:-1])}")
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note WHERE enc_identifier = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if row:
            note_dict = self._row_to_dict(row)
            content_length = len(note_dict.get('content', ''))
            logger.info(f"[get_note] 读取笔记成功: note_id={note_id}, title={note_dict.get('title', '')}, "
                        f"content_length={content_length}, cursor_position={note_dict.get('cursor_position', 0)}, "
                        f"content={note_dict.get('content', '')}")
            return note_dict
        else:
            logger.warning(f"[get_note] 笔记不存在: note_id={note_id}")
        return None
        
    def update_note(self, note_id: str, title: Optional[str] = None, 
                   content: Optional[str] = None, cursor_position: Optional[int] = None):
        """更新笔记
        
        Args:
            note_id: 笔记ID
            title: 标题（可选）
            content: 内容（可选）
            cursor_position: 光标位置（可选）
        """
        logger.info(f"[update_note] 开始更新笔记: note_id={note_id}, title={title}, "
                    f"content_length={len(content) if content else 0}, cursor_position={cursor_position}")
        
        # 动态构建 SET 子句，只更新传入的字段
        fields = []
        params = []
        
        if title is not None:
            fields.append("enc_title = ?")
            params.append(title)
        
        if content is not None:
            fields.append("enc_content = ?")
            params.append(self._encrypt_content(content))
        
        if cursor_position is not None:
            fields.append("enc_cursor_position = ?")
            params.append(cursor_position)
        
        # 始终更新修改时间
        fields.append("enc_modified_at = ?")
        params.append(self._timestamp_to_cocoa(datetime.now()))
        
        params.append(note_id)
        
        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE enc_note SET {', '.join(fields)} WHERE enc_identifier = ?",
            params
        )
        
        if cursor.rowcount == 0:
            logger.warning(f"[update_note] 笔记不存在: note_id={note_id}")
            return
        
        self.conn.commit()
        logger.info(f"[update_note] 笔记更新完成: note_id={note_id}")
        
    def delete_note(self, note_id: str):
        """删除笔记（移到最近删除）"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE enc_note 
            SET enc_is_deleted = 1, enc_modified_at = ?
            WHERE enc_identifier = ?
        ''', (cocoa_time, note_id))
        
        self.conn.commit()
    
    def toggle_pin_note(self, note_id: str):
        """切换笔记的置顶状态"""
        cursor = self.conn.cursor()
        
        # 获取当前置顶状态
        cursor.execute('''
            SELECT enc_is_pinned FROM enc_note WHERE enc_identifier = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if not row:
            return False
        
        current_pinned = row[0]
        new_pinned = 0 if current_pinned else 1
        
        # 更新置顶状态
        cursor.execute('''
            UPDATE enc_note 
            SET enc_is_pinned = ?
            WHERE enc_identifier = ?
        ''', (new_pinned, note_id))
        
        self.conn.commit()
        return new_pinned == 1
    
    def is_note_pinned(self, note_id: str) -> bool:
        """检查笔记是否已置顶"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT enc_is_pinned FROM enc_note WHERE enc_identifier = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        return bool(row[0]) if row else False
        
    def permanently_delete_note(self, note_id: str):
        """永久删除笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM enc_note WHERE enc_identifier = ?
        ''', (note_id,))
        
        self.conn.commit()
        
    def toggle_favorite(self, note_id: str):
        """切换收藏状态"""
        cursor = self.conn.cursor()
        
        # 获取当前状态
        cursor.execute('''
            SELECT enc_is_favorite FROM enc_note WHERE enc_identifier = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if row:
            new_state = 0 if row['enc_is_favorite'] else 1
            cocoa_time = self._timestamp_to_cocoa(datetime.now())
            
            cursor.execute('''
                UPDATE enc_note 
                SET enc_is_favorite = ?, enc_modified_at = ?
                WHERE enc_identifier = ?
            ''', (new_state, cocoa_time, note_id))
            
            self.conn.commit()
            
    def get_all_notes(self) -> List[Dict]:
        """获取所有未删除的笔记（置顶的笔记排在前面）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note 
            WHERE enc_is_deleted = 0
            ORDER BY enc_is_pinned DESC, enc_modified_at DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_favorite_notes(self) -> List[Dict]:
        """获取收藏的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note 
            WHERE enc_is_favorite = 1 AND enc_is_deleted = 0
            ORDER BY enc_modified_at DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_deleted_notes(self) -> List[Dict]:
        """获取已删除的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note 
            WHERE enc_is_deleted = 1
            ORDER BY enc_modified_at DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_by_folder(self, folder_id: str) -> List[Dict]:
        """获取指定文件夹的笔记（置顶的笔记排在前面）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note 
            WHERE enc_folder_id = ? AND enc_is_deleted = 0
            ORDER BY enc_is_pinned DESC, enc_modified_at DESC
        ''', (folder_id,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_modified_after(self, timestamp: float) -> List[Dict]:
        """获取指定时间后修改的笔记（用于同步）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_note 
            WHERE enc_modified_at > ?
            ORDER BY enc_modified_at ASC
        ''', (timestamp,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将数据库行转换为字典（兼容旧接口）"""
        if not row:
            return None
            
        # 转换为旧格式以保持兼容性
        created_at = self._cocoa_to_datetime(row['enc_created_at'])
        updated_at = self._cocoa_to_datetime(row['enc_modified_at'])
        
        # 解密内容
        encrypted_content = row['enc_content'] or ''
        decrypted_content = self._decrypt_content(encrypted_content)
        
        return {
            'id': row['enc_identifier'],
            'folder_id': row['enc_folder_id'],
            'title': row['enc_title'] or '无标题',
            'content': decrypted_content,
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'is_favorite': bool(row['enc_is_favorite']),
            'is_deleted': bool(row['enc_is_deleted']),
            'cursor_position': row['enc_cursor_position'] if row['enc_cursor_position'] is not None else 0,
            # CloudKit字段
            'ck_record_id': row['enc_ck_record_id'],
            'ck_change_tag': row['enc_ck_change_tag'],
            # 数据库内部字段
            '_pk': row['enc_pk'],
            '_cocoa_created': row['enc_created_at'],
            '_cocoa_modified': row['enc_modified_at']
        }
        
    def update_cloudkit_metadata(self, note_id: str, record_id: str, 
                                 change_tag: str, system_fields: bytes = None):
        """更新CloudKit元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE enc_note 
            SET enc_ck_record_id = ?, enc_ck_change_tag = ?, enc_ck_system_fields = ?
            WHERE enc_identifier = ?
        ''', (record_id, change_tag, system_fields, note_id))
        
        self.conn.commit()
        
    def get_sync_metadata(self, key: str) -> Optional[str]:
        """获取同步元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT enc_value FROM enc_ck_metadata WHERE enc_key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        return row['enc_value'] if row else None
        
    def set_sync_metadata(self, key: str, value: str):
        """设置同步元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO enc_ck_metadata (enc_key, enc_value)
            VALUES (?, ?)
        ''', (key, value))
        
        self.conn.commit()
    
    def get_app_state(self, key: str) -> Optional[str]:
        """获取应用状态
        
        Args:
            key: 状态键
            
        Returns:
            状态值，如果不存在则返回None
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT enc_value FROM enc_app_state WHERE enc_key = ?
        ''', (key,))
        
        row = cursor.fetchone()
        return row['enc_value'] if row else None
    
    def set_app_state(self, key: str, value: str):
        """设置应用状态
        
        Args:
            key: 状态键
            value: 状态值
        """
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            INSERT OR REPLACE INTO enc_app_state (enc_key, enc_value, enc_modified_at)
            VALUES (?, ?, ?)
        ''', (key, value, cocoa_time))
        
        self.conn.commit()
    
    def remove_app_state(self, key: str):
        """删除应用状态
        
        Args:
            key: 状态键
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM enc_app_state WHERE enc_key = ?
        ''', (key,))
        
        self.conn.commit()
        
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            
    # ========== 文件夹管理方法 ==========
    
    def create_folder(self, name: str, parent_folder_id: Optional[str] = None) -> str:
        """创建新文件夹
        
        Args:
            name: 文件夹名称
            parent_folder_id: 父文件夹ID，如果为None则创建顶级文件夹
            
        Returns:
            新创建的文件夹ID
        """
        folder_id = str(uuid.uuid4())
        now = datetime.now()
        cocoa_time = self._timestamp_to_cocoa(now)
        
        cursor = self.conn.cursor()
        
        # 获取当前最大的排序索引
        cursor.execute('SELECT MAX(enc_order_index) FROM enc_folder')
        max_order = cursor.fetchone()[0]
        order_index = (max_order or 0) + 1
        
        cursor.execute('''
            INSERT INTO enc_folder (
                enc_identifier, enc_name, enc_parent_folder_id, enc_created_at, 
                enc_modified_at, enc_order_index
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (folder_id, name, parent_folder_id, cocoa_time, cocoa_time, order_index))
        
        self.conn.commit()
        return folder_id
        
    def get_folder(self, folder_id: str) -> Optional[Dict]:
        """获取文件夹"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_folder WHERE enc_identifier = ?
        ''', (folder_id,))
        
        row = cursor.fetchone()
        if row:
            return self._folder_row_to_dict(row)
        return None
        
    def get_all_folders(self) -> List[Dict]:
        """获取所有文件夹"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_folder 
            ORDER BY enc_order_index ASC
        ''')
        
        return [self._folder_row_to_dict(row) for row in cursor.fetchall()]
        
    def update_folder(self, folder_id: str, name: str):
        """更新文件夹名称"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE enc_folder 
            SET enc_name = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
        ''', (name, cocoa_time, folder_id))
        
        self.conn.commit()

    def is_ancestor_folder(self, ancestor_id: str, descendant_id: str) -> bool:
        """检查ancestor_id是否是descendant_id的祖先（包括自己）
        
        Args:
            ancestor_id: 可能的祖先文件夹ID
            descendant_id: 可能的子孙文件夹ID
            
        Returns:
            bool: 如果ancestor_id是descendant_id的祖先或就是自己，返回True
        """
        if not ancestor_id or not descendant_id:
            return False
        
        # 自己是自己的祖先
        if ancestor_id == descendant_id:
            return True
        
        # 获取ancestor_id的所有子孙文件夹
        try:
            descendants = set(self._get_descendant_folder_ids(ancestor_id))
            return descendant_id in descendants
        except Exception:
            return False
    
    def update_folder_parent(self, folder_id: str, parent_folder_id: Optional[str]):
        """更新文件夹父级（用于拖拽：把文件夹移动到另一个文件夹下）。

        规则：
        - parent_folder_id=None 表示移动到顶级。
        - 不允许把文件夹移动到自身或自身的子孙文件夹下（避免环）。
        """
        if not folder_id:
            return

        # 自己不能成为自己的父级
        if parent_folder_id == folder_id:
            return

        # 禁止移动到自己的子孙节点下
        try:
            descendants = set(self._get_descendant_folder_ids(folder_id))
        except Exception:
            descendants = set([folder_id])

        if parent_folder_id and parent_folder_id in descendants:
            return

        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute(
            '''
            UPDATE enc_folder
            SET enc_parent_folder_id = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
            ''',
            (parent_folder_id, cocoa_time, folder_id),
        )
        self.conn.commit()

    def reorder_folder(self, folder_id: str, target_folder_id: str, insert_before: bool) -> bool:
        """调整文件夹顺序（在同级文件夹中移动位置）
        
        Args:
            folder_id: 要移动的文件夹ID
            target_folder_id: 目标文件夹ID（参考位置）
            insert_before: True表示插入到目标之前，False表示插入到目标之后
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if not folder_id or not target_folder_id or folder_id == target_folder_id:
            print(f"[调整顺序] 参数无效: folder_id={folder_id}, target_folder_id={target_folder_id}")
            return False
        
        cursor = self.conn.cursor()
        
        # 获取源文件夹和目标文件夹的信息
        src_folder = self.get_folder(folder_id)
        target_folder = self.get_folder(target_folder_id)
        
        if not src_folder or not target_folder:
            print(f"[调整顺序] 文件夹不存在: src_folder={src_folder}, target_folder={target_folder}")
            return False
        
        # 检查是否在同一父文件夹下
        src_parent = src_folder.get('parent_folder_id')
        target_parent = target_folder.get('parent_folder_id')
        
        print(f"[调整顺序] 源文件夹父级: {src_parent}, 目标文件夹父级: {target_parent}")
        
        if src_parent != target_parent:
            # 不在同一父文件夹下，不能调整顺序
            print(f"[调整顺序] 失败：不在同一父文件夹下")
            return False
        
        # 获取目标文件夹的order_index
        target_order = target_folder.get('order_index', 0)
        
        # 计算新的order_index
        if insert_before:
            # 插入到目标之前
            new_order = target_order - 0.5
        else:
            # 插入到目标之后
            new_order = target_order + 0.5
        
        # 更新源文件夹的order_index
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute('''
            UPDATE enc_folder
            SET enc_order_index = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
        ''', (new_order, cocoa_time, folder_id))
        
        print(f"[调整顺序] 成功：将文件夹 {folder_id} 的order_index从 {src_folder.get('order_index')} 改为 {new_order}")
        
        self.conn.commit()
        
        # 重新规范化所有文件夹的order_index（避免浮点数累积）
        self._normalize_folder_order_indices()
        
        return True
    
    def _normalize_folder_order_indices(self):
        """重新规范化所有文件夹的order_index，使其变为连续的整数"""
        cursor = self.conn.cursor()
        
        # 按当前order_index排序，重新分配连续的整数
        cursor.execute('''
            SELECT enc_identifier FROM enc_folder
            ORDER BY enc_order_index ASC, enc_created_at ASC
        ''')
        
        folders = cursor.fetchall()
        for idx, row in enumerate(folders):
            folder_id = row[0] if isinstance(row, tuple) else row['enc_identifier']
            cursor.execute('''
                UPDATE enc_folder
                SET enc_order_index = ?
                WHERE enc_identifier = ?
            ''', (idx + 1, folder_id))
        
        self.conn.commit()

        
    def delete_folder(self, folder_id: str):
        """删除文件夹（将其中的笔记移到无文件夹）"""
        cursor = self.conn.cursor()
        
        # 将文件夹中的笔记移到无文件夹
        cursor.execute('''
            UPDATE enc_note 
            SET enc_folder_id = NULL
            WHERE enc_folder_id = ?
        ''', (folder_id,))
        
        # 删除文件夹
        cursor.execute('''
            DELETE FROM enc_folder WHERE enc_identifier = ?
        ''', (folder_id,))
        
        self.conn.commit()
        
    def restore_note(self, note_id: str):
        """从“最近删除”恢复笔记（enc_is_deleted=0）。"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute(
            '''
            UPDATE enc_note
            SET enc_is_deleted = 0, enc_modified_at = ?
            WHERE enc_identifier = ?
            ''',
            (cocoa_time, note_id),
        )
        self.conn.commit()

    def move_note_to_folder(self, note_id: str, folder_id: Optional[str]):
        """将笔记移动到文件夹。

        约定：
        - “最近删除”由 `enc_is_deleted=1` 表示。
        - 如果一条已删除笔记被移动到“所有笔记/任意文件夹”，则视为“恢复并移动”。
        """
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())

        # 先恢复（如果它在最近删除里）
        cursor.execute('SELECT enc_is_deleted FROM enc_note WHERE enc_identifier = ?', (note_id,))
        row = cursor.fetchone()
        try:
            is_deleted = bool(row['enc_is_deleted']) if row is not None else False
        except Exception:
            is_deleted = bool(row[0]) if row is not None else False

        if is_deleted:
            cursor.execute(
                '''
                UPDATE enc_note
                SET enc_is_deleted = 0, enc_modified_at = ?
                WHERE enc_identifier = ?
                ''',
                (cocoa_time, note_id),
            )

        # 再更新所属文件夹
        cursor.execute(
            '''
            UPDATE enc_note
            SET enc_folder_id = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
            ''',
            (folder_id, cocoa_time, note_id),
        )

        self.conn.commit()

        
    def _folder_row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将文件夹数据库行转换为字典"""
        if not row:
            return None
            
        created_at = self._cocoa_to_datetime(row['enc_created_at'])
        updated_at = self._cocoa_to_datetime(row['enc_modified_at'])
        
        # 安全获取enc_last_note_id字段（可能不存在于旧数据库）
        try:
            last_note_id = row['enc_last_note_id'] if row['enc_last_note_id'] else None
        except (KeyError, IndexError):
            last_note_id = None
        
        return {
            'id': row['enc_identifier'],
            'name': row['enc_name'],
            'parent_folder_id': row['enc_parent_folder_id'] if row['enc_parent_folder_id'] else None,
            'last_note_id': last_note_id,
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'order_index': row['enc_order_index'],
            '_pk': row['enc_pk'],
            '_cocoa_created': row['enc_created_at'],
            '_cocoa_modified': row['enc_modified_at']
        }
    
    # ========== 标签管理方法 ==========
    
    def create_tag(self, name: str) -> str:
        """创建新标签"""
        tag_id = str(uuid.uuid4())
        now = datetime.now()
        cocoa_time = self._timestamp_to_cocoa(now)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO enc_tag (
                enc_identifier, enc_name, enc_created_at, enc_modified_at
            ) VALUES (?, ?, ?, ?)
        ''', (tag_id, name, cocoa_time, cocoa_time))
        
        self.conn.commit()
        return tag_id
        
    def get_tag(self, tag_id: str) -> Optional[Dict]:
        """获取标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_tag WHERE enc_identifier = ?
        ''', (tag_id,))
        
        row = cursor.fetchone()
        if row:
            return self._tag_row_to_dict(row)
        return None
        
    def get_all_tags(self) -> List[Dict]:
        """获取所有标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM enc_tag 
            ORDER BY enc_name ASC
        ''')
        
        return [self._tag_row_to_dict(row) for row in cursor.fetchall()]
        
    def update_tag(self, tag_id: str, name: str):
        """更新标签名称"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE enc_tag 
            SET enc_name = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
        ''', (name, cocoa_time, tag_id))
        
        self.conn.commit()
        
    def delete_tag(self, tag_id: str):
        """删除标签（同时删除关联关系）"""
        cursor = self.conn.cursor()
        
        # 删除笔记-标签关联
        cursor.execute('''
            DELETE FROM enc_note_tag WHERE enc_tag_id = ?
        ''', (tag_id,))
        
        # 删除标签
        cursor.execute('''
            DELETE FROM enc_tag WHERE enc_identifier = ?
        ''', (tag_id,))
        
        self.conn.commit()
        
    def add_tag_to_note(self, note_id: str, tag_id: str):
        """为笔记添加标签"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO enc_note_tag (enc_note_id, enc_tag_id)
                VALUES (?, ?)
            ''', (note_id, tag_id))
            self.conn.commit()
        except sqlite3.IntegrityError:
            # 关联已存在，忽略
            pass
            
    def remove_tag_from_note(self, note_id: str, tag_id: str):
        """从笔记移除标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM enc_note_tag 
            WHERE enc_note_id = ? AND enc_tag_id = ?
        ''', (note_id, tag_id))
        
        self.conn.commit()
        
    def get_note_tags(self, note_id: str) -> List[Dict]:
        """获取笔记的所有标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.* FROM enc_tag t
            INNER JOIN enc_note_tag nt ON t.enc_identifier = nt.enc_tag_id
            WHERE nt.enc_note_id = ?
            ORDER BY t.enc_name ASC
        ''', (note_id,))
        
        return [self._tag_row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_by_tag(self, tag_id: str) -> List[Dict]:
        """获取带有指定标签的所有笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT n.* FROM enc_note n
            INNER JOIN enc_note_tag nt ON n.enc_identifier = nt.enc_note_id
            WHERE nt.enc_tag_id = ? AND n.enc_is_deleted = 0
            ORDER BY n.enc_modified_at DESC
        ''', (tag_id,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_tag_count(self, tag_id: str) -> int:
        """获取标签下的笔记数量"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM enc_note_tag nt
            INNER JOIN enc_note n ON nt.enc_note_id = n.enc_identifier
            WHERE nt.enc_tag_id = ? AND n.enc_is_deleted = 0
        ''', (tag_id,))
        
        row = cursor.fetchone()
        return row['count'] if row else 0
        
    def _tag_row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将标签数据库行转换为字典"""
        if not row:
            return None
            
        created_at = self._cocoa_to_datetime(row['enc_created_at'])
        updated_at = self._cocoa_to_datetime(row['enc_modified_at'])
        
        return {
            'id': row['enc_identifier'],
            'name': row['enc_name'],
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            '_pk': row['enc_pk'],
            '_cocoa_created': row['enc_created_at'],
            '_cocoa_modified': row['enc_modified_at']
        }
    
    def _encrypt_content(self, content: str) -> str:
        """
        加密笔记内容

        说明：
        - 某些输入法/富文本编辑器在极端情况下可能产生“孤立代理项”(surrogate)
          （例如 \ud83d 这样的半个emoji）。Python 的 UTF-8 编码默认不允许
          surrogate，直接加密会触发 `UnicodeEncodeError: surrogates not allowed`。
        - 这里统一在入库前做一次清洗，避免笔记自动保存时崩溃。

        Args:
            content: 明文内容

        Returns:
            加密后的内容（如果加密已启用）或原内容
        """
        if content is None:
            content = ""

        # 清理非法 surrogate：尽量保留其它字符，遇到孤立 surrogate 用 U+FFFD 替换
        try:
            content = content.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')
        except Exception:
            # 兜底：即便 encode/decode 失败，也不要让保存流程崩溃
            try:
                content = (content or "").encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            except Exception:
                content = ""

        if self.encryption_manager.is_unlocked:
            try:
                return self.encryption_manager.encrypt(content)
            except Exception as e:
                print(f"加密内容失败: {e}")
                return content
        return content

        
    def _decrypt_content(self, encrypted_content: str) -> str:
        """
        解密笔记内容
        
        Args:
            encrypted_content: 加密的内容
            
        Returns:
            解密后的内容（如果加密已启用）或原内容
        """
        if not encrypted_content:
            return ''
            
        if self.encryption_manager.is_unlocked:
            try:
                return self.encryption_manager.decrypt(encrypted_content)
            except Exception as e:
                # 如果解密失败，可能是未加密的旧数据
                print(f"解密内容失败，返回原内容: {e}")
                return encrypted_content
        return encrypted_content
        
    def re_encrypt_all_notes(self):
        """
        重新加密所有笔记（用于修改密码后）
        
        Returns:
            重新加密的笔记数量
        """
        if not self.encryption_manager.is_unlocked:
            return 0
            
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM enc_note')
        
        count = 0
        for row in cursor.fetchall():
            try:
                # 获取笔记内容（已解密）
                note = self._row_to_dict(row)
                content = note['content']
                
                # 重新加密
                encrypted_content = self._encrypt_content(content)
                
                # 更新数据库
                cursor.execute('''
                    UPDATE enc_note SET enc_content = ? WHERE enc_identifier = ?
                ''', (encrypted_content, note['id']))
                
                count += 1
            except Exception as e:
                print(f"重新加密笔记失败 {row['enc_identifier']}: {e}")
                
        self.conn.commit()
        return count

    def _get_descendant_folder_ids(self, folder_id: str) -> List[str]:
        """获取folder_id的所有子文件夹ID（递归，包含自身）。"""
        if not folder_id:
            return []

        try:
            all_folders = self.get_all_folders()
        except Exception:
            all_folders = []

        children_map: Dict[str, List[str]] = {}
        for f in all_folders:
            pid = f.get('parent_folder_id')
            if not pid:
                continue
            children_map.setdefault(pid, []).append(f.get('id'))

        result: List[str] = []
        stack: List[str] = [folder_id]
        seen: set[str] = set()

        while stack:
            cur = stack.pop()
            if not cur or cur in seen:
                continue
            seen.add(cur)
            result.append(cur)
            for child in children_map.get(cur, []):
                if child and child not in seen:
                    stack.append(child)

        return result

    def delete_notes_in_folders(self, folder_ids: List[str]):
        """将指定folder_ids下的所有笔记移到回收站（enc_is_deleted=1）。"""
        if not folder_ids:
            return

        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        placeholders = ",".join(["?"] * len(folder_ids))

        cursor.execute(
            f"""
            UPDATE enc_note
            SET enc_is_deleted = 1, enc_modified_at = ?
            WHERE enc_is_deleted = 0 AND enc_folder_id IN ({placeholders})
            """,
            (cocoa_time, *folder_ids),
        )
        self.conn.commit()

    def delete_folder_to_trash(self, folder_id: str):
        """删除文件夹：将该文件夹（含子文件夹）下的笔记全部移入"最近删除"，然后删除文件夹本身。

        说明：
        - "最近删除"在本项目里由笔记字段 `enc_is_deleted=1` 表示，而不是一个真实文件夹。
        - 文件夹删除后，其子文件夹也会一并删除。
        """
        if not folder_id:
            return

        # 1) 获取子树folder ids
        folder_ids = self._get_descendant_folder_ids(folder_id)
        if not folder_ids:
            folder_ids = [folder_id]

        # 2) 笔记移入最近删除
        self.delete_notes_in_folders(folder_ids)

        # 3) 删除文件夹子树（先删子后删父）
        cursor = self.conn.cursor()
        for fid in reversed(folder_ids):
            cursor.execute('DELETE FROM enc_folder WHERE enc_identifier = ?', (fid,))
        self.conn.commit()
    
    def get_folder_last_note_id(self, folder_id: str) -> Optional[str]:
        """获取文件夹的上次编辑笔记ID
        
        Args:
            folder_id: 文件夹ID
            
        Returns:
            上次编辑的笔记ID，如果没有则返回None
        """
        if not folder_id:
            return None
            
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT enc_last_note_id FROM enc_folder WHERE enc_identifier = ?
        ''', (folder_id,))
        
        row = cursor.fetchone()
        if row:
            try:
                return row['enc_last_note_id'] if row['enc_last_note_id'] else None
            except (KeyError, IndexError):
                return None
        return None
    
    def set_folder_last_note_id(self, folder_id: str, note_id: Optional[str]):
        """设置文件夹的上次编辑笔记ID
        
        Args:
            folder_id: 文件夹ID
            note_id: 笔记ID，可以为None
        """
        if not folder_id:
            return
            
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE enc_folder
            SET enc_last_note_id = ?, enc_modified_at = ?
            WHERE enc_identifier = ?
        ''', (note_id, cocoa_time, folder_id))
        
        self.conn.commit()
    
    def __del__(self):
        """析构函数，确保数据库连接关闭"""
        self.close()