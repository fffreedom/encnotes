#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
笔记管理器 - 使用SQLite数据库存储笔记
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from encryption_manager import EncryptionManager
from attachment_manager import AttachmentManager


class NoteManager:
    """笔记管理器类 - 使用SQLite数据库"""
    
    def __init__(self):
        # 数据存储路径 - 模仿macOS备忘录的存储位置
        self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / "NoteStore.sqlite"
        self.conn = None
        
        # 初始化加密管理器
        self.encryption_manager = EncryptionManager()
        
        # 初始化附件管理器
        self.attachment_manager = AttachmentManager(self.encryption_manager)
        
        self.init_database()
        
    def init_database(self):
        """初始化数据库，创建表结构"""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        
        cursor = self.conn.cursor()
        
        # 创建文件夹表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ZFOLDER (
                Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
                Z_ENT INTEGER DEFAULT 2,
                Z_OPT INTEGER DEFAULT 1,
                ZIDENTIFIER TEXT UNIQUE NOT NULL,
                ZNAME TEXT NOT NULL,
                ZPARENTFOLDERID TEXT,
                ZCREATIONDATE REAL,
                ZMODIFICATIONDATE REAL,
                ZORDERINDEX INTEGER DEFAULT 0,
                FOREIGN KEY (ZPARENTFOLDERID) REFERENCES ZFOLDER(ZIDENTIFIER)
            )
        ''')
        
        # 创建笔记表 - 模仿备忘录的表结构
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ZNOTE (
                Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
                Z_ENT INTEGER DEFAULT 1,
                Z_OPT INTEGER DEFAULT 1,
                ZIDENTIFIER TEXT UNIQUE NOT NULL,
                ZFOLDERID TEXT,
                ZTITLE TEXT,
                ZCONTENT TEXT,
                ZCREATIONDATE REAL,
                ZMODIFICATIONDATE REAL,
                ZISFAVORITE INTEGER DEFAULT 0,
                ZISDELETED INTEGER DEFAULT 0,
                ZISPINNED INTEGER DEFAULT 0,
                ZCURSORPOSITION INTEGER DEFAULT 0,
                ZCKRECORDID TEXT,
                ZCKRECORDCHANGETAG TEXT,
                ZCKRECORDSYSTEMFIELDS BLOB,
                FOREIGN KEY (ZFOLDERID) REFERENCES ZFOLDER(ZIDENTIFIER)
            )
        ''')
        
        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZIDENTIFIER_INDEX 
            ON ZNOTE(ZIDENTIFIER)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZMODIFICATIONDATE_INDEX 
            ON ZNOTE(ZMODIFICATIONDATE DESC)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZISFAVORITE_INDEX 
            ON ZNOTE(ZISFAVORITE)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZISDELETED_INDEX 
            ON ZNOTE(ZISDELETED)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZFOLDERID_INDEX 
            ON ZNOTE(ZFOLDERID)
        ''')
        
        # 创建文件夹索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZFOLDER_IDENTIFIER_INDEX 
            ON ZFOLDER(ZIDENTIFIER)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZFOLDER_ORDERINDEX_INDEX 
            ON ZFOLDER(ZORDERINDEX)
        ''')
        
        # 创建CloudKit同步元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ZCKMETADATA (
                Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
                ZKEY TEXT UNIQUE NOT NULL,
                ZVALUE TEXT
            )
        ''')
        
        # 创建标签表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ZTAG (
                Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
                Z_ENT INTEGER DEFAULT 3,
                Z_OPT INTEGER DEFAULT 1,
                ZIDENTIFIER TEXT UNIQUE NOT NULL,
                ZNAME TEXT NOT NULL,
                ZCREATIONDATE REAL,
                ZMODIFICATIONDATE REAL
            )
        ''')
        
        # 创建笔记-标签关联表（多对多关系）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ZNOTETAG (
                Z_PK INTEGER PRIMARY KEY AUTOINCREMENT,
                ZNOTEID TEXT NOT NULL,
                ZTAGID TEXT NOT NULL,
                FOREIGN KEY (ZNOTEID) REFERENCES ZNOTE(ZIDENTIFIER),
                FOREIGN KEY (ZTAGID) REFERENCES ZTAG(ZIDENTIFIER),
                UNIQUE(ZNOTEID, ZTAGID)
            )
        ''')
        
        # 创建标签索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZTAG_IDENTIFIER_INDEX 
            ON ZTAG(ZIDENTIFIER)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZNOTETAG_NOTEID_INDEX 
            ON ZNOTETAG(ZNOTEID)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS ZNOTETAG_TAGID_INDEX 
            ON ZNOTETAG(ZTAGID)
        ''')
        
        # 数据库迁移：为现有数据库添加ZPARENTFOLDERID字段
        try:
            # 检查ZFOLDER表是否已有ZPARENTFOLDERID字段
            cursor.execute("PRAGMA table_info(ZFOLDER)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'ZPARENTFOLDERID' not in columns:
                # 添加ZPARENTFOLDERID字段
                cursor.execute('''
                    ALTER TABLE ZFOLDER ADD COLUMN ZPARENTFOLDERID TEXT
                ''')
                print("数据库迁移：已添加ZPARENTFOLDERID字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")
        
        # 数据库迁移：为现有数据库添加ZISPINNED字段
        try:
            # 检查ZNOTE表是否已有ZISPINNED字段
            cursor.execute("PRAGMA table_info(ZNOTE)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'ZISPINNED' not in columns:
                # 添加ZISPINNED字段
                cursor.execute('''
                    ALTER TABLE ZNOTE ADD COLUMN ZISPINNED INTEGER DEFAULT 0
                ''')
                print("数据库迁移：已添加ZISPINNED字段")
        except Exception as e:
            print(f"数据库迁移警告: {e}")
        
        # 数据库迁移：为现有数据库添加ZCURSORPOSITION字段
        try:
            # 检查ZNOTE表是否已有ZCURSORPOSITION字段
            cursor.execute("PRAGMA table_info(ZNOTE)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'ZCURSORPOSITION' not in columns:
                # 添加ZCURSORPOSITION字段
                cursor.execute('''
                    ALTER TABLE ZNOTE ADD COLUMN ZCURSORPOSITION INTEGER DEFAULT 0
                ''')
                print("数据库迁移：已添加ZCURSORPOSITION字段")
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
            INSERT INTO ZNOTE (
                ZIDENTIFIER, ZFOLDERID, ZTITLE, ZCONTENT, 
                ZCREATIONDATE, ZMODIFICATIONDATE,
                ZISFAVORITE, ZISDELETED
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        ''', (note_id, folder_id, title, encrypted_content, cocoa_time, cocoa_time))
        
        self.conn.commit()
        return note_id
        
    def get_note(self, note_id: str) -> Optional[Dict]:
        """获取笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE WHERE ZIDENTIFIER = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if row:
            return self._row_to_dict(row)
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
        cursor = self.conn.cursor()
        
        # 获取当前笔记
        note = self.get_note(note_id)
        if not note:
            return
            
        # 更新字段
        if title is not None:
            cursor.execute('''
                UPDATE ZNOTE SET ZTITLE = ? WHERE ZIDENTIFIER = ?
            ''', (title, note_id))
            
        if content is not None:
            # 加密内容
            encrypted_content = self._encrypt_content(content)
            cursor.execute('''
                UPDATE ZNOTE SET ZCONTENT = ? WHERE ZIDENTIFIER = ?
            ''', (encrypted_content, note_id))
        
        if cursor_position is not None:
            cursor.execute('''
                UPDATE ZNOTE SET ZCURSORPOSITION = ? WHERE ZIDENTIFIER = ?
            ''', (cursor_position, note_id))
            
        # 更新修改时间
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute('''
            UPDATE ZNOTE SET ZMODIFICATIONDATE = ? WHERE ZIDENTIFIER = ?
        ''', (cocoa_time, note_id))
        
        self.conn.commit()
        
    def delete_note(self, note_id: str):
        """删除笔记（移到最近删除）"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZISDELETED = 1, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
        ''', (cocoa_time, note_id))
        
        self.conn.commit()
    
    def toggle_pin_note(self, note_id: str):
        """切换笔记的置顶状态"""
        cursor = self.conn.cursor()
        
        # 获取当前置顶状态
        cursor.execute('''
            SELECT ZISPINNED FROM ZNOTE WHERE ZIDENTIFIER = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if not row:
            return False
        
        current_pinned = row[0]
        new_pinned = 0 if current_pinned else 1
        
        # 更新置顶状态
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZISPINNED = ?
            WHERE ZIDENTIFIER = ?
        ''', (new_pinned, note_id))
        
        self.conn.commit()
        return new_pinned == 1
    
    def is_note_pinned(self, note_id: str) -> bool:
        """检查笔记是否已置顶"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ZISPINNED FROM ZNOTE WHERE ZIDENTIFIER = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        return bool(row[0]) if row else False
        
    def permanently_delete_note(self, note_id: str):
        """永久删除笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM ZNOTE WHERE ZIDENTIFIER = ?
        ''', (note_id,))
        
        self.conn.commit()
        
    def toggle_favorite(self, note_id: str):
        """切换收藏状态"""
        cursor = self.conn.cursor()
        
        # 获取当前状态
        cursor.execute('''
            SELECT ZISFAVORITE FROM ZNOTE WHERE ZIDENTIFIER = ?
        ''', (note_id,))
        
        row = cursor.fetchone()
        if row:
            new_state = 0 if row['ZISFAVORITE'] else 1
            cocoa_time = self._timestamp_to_cocoa(datetime.now())
            
            cursor.execute('''
                UPDATE ZNOTE 
                SET ZISFAVORITE = ?, ZMODIFICATIONDATE = ?
                WHERE ZIDENTIFIER = ?
            ''', (new_state, cocoa_time, note_id))
            
            self.conn.commit()
            
    def get_all_notes(self) -> List[Dict]:
        """获取所有未删除的笔记（置顶的笔记排在前面）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZISDELETED = 0
            ORDER BY ZISPINNED DESC, ZMODIFICATIONDATE DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_favorite_notes(self) -> List[Dict]:
        """获取收藏的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZISFAVORITE = 1 AND ZISDELETED = 0
            ORDER BY ZMODIFICATIONDATE DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_deleted_notes(self) -> List[Dict]:
        """获取已删除的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZISDELETED = 1
            ORDER BY ZMODIFICATIONDATE DESC
        ''')
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_by_folder(self, folder_id: str) -> List[Dict]:
        """获取指定文件夹的笔记（置顶的笔记排在前面）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZFOLDERID = ? AND ZISDELETED = 0
            ORDER BY ZISPINNED DESC, ZMODIFICATIONDATE DESC
        ''', (folder_id,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_modified_after(self, timestamp: float) -> List[Dict]:
        """获取指定时间后修改的笔记（用于同步）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZMODIFICATIONDATE > ?
            ORDER BY ZMODIFICATIONDATE ASC
        ''', (timestamp,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将数据库行转换为字典（兼容旧接口）"""
        if not row:
            return None
            
        # 转换为旧格式以保持兼容性
        created_at = self._cocoa_to_datetime(row['ZCREATIONDATE'])
        updated_at = self._cocoa_to_datetime(row['ZMODIFICATIONDATE'])
        
        # 解密内容
        encrypted_content = row['ZCONTENT'] or ''
        decrypted_content = self._decrypt_content(encrypted_content)
        
        return {
            'id': row['ZIDENTIFIER'],
            'folder_id': row['ZFOLDERID'],
            'title': row['ZTITLE'] or '无标题',
            'content': decrypted_content,
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'is_favorite': bool(row['ZISFAVORITE']),
            'is_deleted': bool(row['ZISDELETED']),
            # CloudKit字段
            'ck_record_id': row['ZCKRECORDID'],
            'ck_change_tag': row['ZCKRECORDCHANGETAG'],
            # 数据库内部字段
            '_pk': row['Z_PK'],
            '_cocoa_created': row['ZCREATIONDATE'],
            '_cocoa_modified': row['ZMODIFICATIONDATE']
        }
        
    def update_cloudkit_metadata(self, note_id: str, record_id: str, 
                                 change_tag: str, system_fields: bytes = None):
        """更新CloudKit元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZCKRECORDID = ?, ZCKRECORDCHANGETAG = ?, ZCKRECORDSYSTEMFIELDS = ?
            WHERE ZIDENTIFIER = ?
        ''', (record_id, change_tag, system_fields, note_id))
        
        self.conn.commit()
        
    def get_sync_metadata(self, key: str) -> Optional[str]:
        """获取同步元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT ZVALUE FROM ZCKMETADATA WHERE ZKEY = ?
        ''', (key,))
        
        row = cursor.fetchone()
        return row['ZVALUE'] if row else None
        
    def set_sync_metadata(self, key: str, value: str):
        """设置同步元数据"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO ZCKMETADATA (ZKEY, ZVALUE)
            VALUES (?, ?)
        ''', (key, value))
        
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
        cursor.execute('SELECT MAX(ZORDERINDEX) FROM ZFOLDER')
        max_order = cursor.fetchone()[0]
        order_index = (max_order or 0) + 1
        
        cursor.execute('''
            INSERT INTO ZFOLDER (
                ZIDENTIFIER, ZNAME, ZPARENTFOLDERID, ZCREATIONDATE, 
                ZMODIFICATIONDATE, ZORDERINDEX
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (folder_id, name, parent_folder_id, cocoa_time, cocoa_time, order_index))
        
        self.conn.commit()
        return folder_id
        
    def get_folder(self, folder_id: str) -> Optional[Dict]:
        """获取文件夹"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZFOLDER WHERE ZIDENTIFIER = ?
        ''', (folder_id,))
        
        row = cursor.fetchone()
        if row:
            return self._folder_row_to_dict(row)
        return None
        
    def get_all_folders(self) -> List[Dict]:
        """获取所有文件夹"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZFOLDER 
            ORDER BY ZORDERINDEX ASC
        ''')
        
        return [self._folder_row_to_dict(row) for row in cursor.fetchall()]
        
    def update_folder(self, folder_id: str, name: str):
        """更新文件夹名称"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE ZFOLDER 
            SET ZNAME = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
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
            UPDATE ZFOLDER
            SET ZPARENTFOLDERID = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
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
            UPDATE ZFOLDER
            SET ZORDERINDEX = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
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
            SELECT ZIDENTIFIER FROM ZFOLDER
            ORDER BY ZORDERINDEX ASC, ZCREATIONDATE ASC
        ''')
        
        folders = cursor.fetchall()
        for idx, row in enumerate(folders):
            folder_id = row[0] if isinstance(row, tuple) else row['ZIDENTIFIER']
            cursor.execute('''
                UPDATE ZFOLDER
                SET ZORDERINDEX = ?
                WHERE ZIDENTIFIER = ?
            ''', (idx + 1, folder_id))
        
        self.conn.commit()

        
    def delete_folder(self, folder_id: str):
        """删除文件夹（将其中的笔记移到无文件夹）"""
        cursor = self.conn.cursor()
        
        # 将文件夹中的笔记移到无文件夹
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZFOLDERID = NULL
            WHERE ZFOLDERID = ?
        ''', (folder_id,))
        
        # 删除文件夹
        cursor.execute('''
            DELETE FROM ZFOLDER WHERE ZIDENTIFIER = ?
        ''', (folder_id,))
        
        self.conn.commit()
        
    def restore_note(self, note_id: str):
        """从“最近删除”恢复笔记（ZISDELETED=0）。"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute(
            '''
            UPDATE ZNOTE
            SET ZISDELETED = 0, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
            ''',
            (cocoa_time, note_id),
        )
        self.conn.commit()

    def move_note_to_folder(self, note_id: str, folder_id: Optional[str]):
        """将笔记移动到文件夹。

        约定：
        - “最近删除”由 `ZISDELETED=1` 表示。
        - 如果一条已删除笔记被移动到“所有笔记/任意文件夹”，则视为“恢复并移动”。
        """
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())

        # 先恢复（如果它在最近删除里）
        cursor.execute('SELECT ZISDELETED FROM ZNOTE WHERE ZIDENTIFIER = ?', (note_id,))
        row = cursor.fetchone()
        try:
            is_deleted = bool(row['ZISDELETED']) if row is not None else False
        except Exception:
            is_deleted = bool(row[0]) if row is not None else False

        if is_deleted:
            cursor.execute(
                '''
                UPDATE ZNOTE
                SET ZISDELETED = 0, ZMODIFICATIONDATE = ?
                WHERE ZIDENTIFIER = ?
                ''',
                (cocoa_time, note_id),
            )

        # 再更新所属文件夹
        cursor.execute(
            '''
            UPDATE ZNOTE
            SET ZFOLDERID = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
            ''',
            (folder_id, cocoa_time, note_id),
        )

        self.conn.commit()

        
    def _folder_row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将文件夹数据库行转换为字典"""
        if not row:
            return None
            
        created_at = self._cocoa_to_datetime(row['ZCREATIONDATE'])
        updated_at = self._cocoa_to_datetime(row['ZMODIFICATIONDATE'])
        
        return {
            'id': row['ZIDENTIFIER'],
            'name': row['ZNAME'],
            'parent_folder_id': row['ZPARENTFOLDERID'] if row['ZPARENTFOLDERID'] else None,
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'order_index': row['ZORDERINDEX'],
            '_pk': row['Z_PK'],
            '_cocoa_created': row['ZCREATIONDATE'],
            '_cocoa_modified': row['ZMODIFICATIONDATE']
        }
    
    # ========== 标签管理方法 ==========
    
    def create_tag(self, name: str) -> str:
        """创建新标签"""
        tag_id = str(uuid.uuid4())
        now = datetime.now()
        cocoa_time = self._timestamp_to_cocoa(now)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO ZTAG (
                ZIDENTIFIER, ZNAME, ZCREATIONDATE, ZMODIFICATIONDATE
            ) VALUES (?, ?, ?, ?)
        ''', (tag_id, name, cocoa_time, cocoa_time))
        
        self.conn.commit()
        return tag_id
        
    def get_tag(self, tag_id: str) -> Optional[Dict]:
        """获取标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZTAG WHERE ZIDENTIFIER = ?
        ''', (tag_id,))
        
        row = cursor.fetchone()
        if row:
            return self._tag_row_to_dict(row)
        return None
        
    def get_all_tags(self) -> List[Dict]:
        """获取所有标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZTAG 
            ORDER BY ZNAME ASC
        ''')
        
        return [self._tag_row_to_dict(row) for row in cursor.fetchall()]
        
    def update_tag(self, tag_id: str, name: str):
        """更新标签名称"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE ZTAG 
            SET ZNAME = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
        ''', (name, cocoa_time, tag_id))
        
        self.conn.commit()
        
    def delete_tag(self, tag_id: str):
        """删除标签（同时删除关联关系）"""
        cursor = self.conn.cursor()
        
        # 删除笔记-标签关联
        cursor.execute('''
            DELETE FROM ZNOTETAG WHERE ZTAGID = ?
        ''', (tag_id,))
        
        # 删除标签
        cursor.execute('''
            DELETE FROM ZTAG WHERE ZIDENTIFIER = ?
        ''', (tag_id,))
        
        self.conn.commit()
        
    def add_tag_to_note(self, note_id: str, tag_id: str):
        """为笔记添加标签"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO ZNOTETAG (ZNOTEID, ZTAGID)
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
            DELETE FROM ZNOTETAG 
            WHERE ZNOTEID = ? AND ZTAGID = ?
        ''', (note_id, tag_id))
        
        self.conn.commit()
        
    def get_note_tags(self, note_id: str) -> List[Dict]:
        """获取笔记的所有标签"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.* FROM ZTAG t
            INNER JOIN ZNOTETAG nt ON t.ZIDENTIFIER = nt.ZTAGID
            WHERE nt.ZNOTEID = ?
            ORDER BY t.ZNAME ASC
        ''', (note_id,))
        
        return [self._tag_row_to_dict(row) for row in cursor.fetchall()]
        
    def get_notes_by_tag(self, tag_id: str) -> List[Dict]:
        """获取带有指定标签的所有笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT n.* FROM ZNOTE n
            INNER JOIN ZNOTETAG nt ON n.ZIDENTIFIER = nt.ZNOTEID
            WHERE nt.ZTAGID = ? AND n.ZISDELETED = 0
            ORDER BY n.ZMODIFICATIONDATE DESC
        ''', (tag_id,))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
        
    def get_tag_count(self, tag_id: str) -> int:
        """获取标签下的笔记数量"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM ZNOTETAG nt
            INNER JOIN ZNOTE n ON nt.ZNOTEID = n.ZIDENTIFIER
            WHERE nt.ZTAGID = ? AND n.ZISDELETED = 0
        ''', (tag_id,))
        
        row = cursor.fetchone()
        return row['count'] if row else 0
        
    def _tag_row_to_dict(self, row: sqlite3.Row) -> Dict:
        """将标签数据库行转换为字典"""
        if not row:
            return None
            
        created_at = self._cocoa_to_datetime(row['ZCREATIONDATE'])
        updated_at = self._cocoa_to_datetime(row['ZMODIFICATIONDATE'])
        
        return {
            'id': row['ZIDENTIFIER'],
            'name': row['ZNAME'],
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            '_pk': row['Z_PK'],
            '_cocoa_created': row['ZCREATIONDATE'],
            '_cocoa_modified': row['ZMODIFICATIONDATE']
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
        cursor.execute('SELECT * FROM ZNOTE')
        
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
                    UPDATE ZNOTE SET ZCONTENT = ? WHERE ZIDENTIFIER = ?
                ''', (encrypted_content, note['id']))
                
                count += 1
            except Exception as e:
                print(f"重新加密笔记失败 {row['ZIDENTIFIER']}: {e}")
                
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
        """将指定folder_ids下的所有笔记移到回收站（ZISDELETED=1）。"""
        if not folder_ids:
            return

        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        placeholders = ",".join(["?"] * len(folder_ids))

        cursor.execute(
            f"""
            UPDATE ZNOTE
            SET ZISDELETED = 1, ZMODIFICATIONDATE = ?
            WHERE ZISDELETED = 0 AND ZFOLDERID IN ({placeholders})
            """,
            (cocoa_time, *folder_ids),
        )
        self.conn.commit()

    def delete_folder_to_trash(self, folder_id: str):
        """删除文件夹：将该文件夹（含子文件夹）下的笔记全部移入“最近删除”，然后删除文件夹本身。

        说明：
        - “最近删除”在本项目里由笔记字段 `ZISDELETED=1` 表示，而不是一个真实文件夹。
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
            cursor.execute('DELETE FROM ZFOLDER WHERE ZIDENTIFIER = ?', (fid,))
        self.conn.commit()
    
    def __del__(self):
        """析构函数，确保数据库连接关闭"""
        self.close()