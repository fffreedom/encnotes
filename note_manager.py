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


class NoteManager:
    """笔记管理器类 - 使用SQLite数据库"""
    
    def __init__(self):
        # 数据存储路径 - 模仿macOS备忘录的存储位置
        self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.mathnotes"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / "NoteStore.sqlite"
        self.conn = None
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
                ZCREATIONDATE REAL,
                ZMODIFICATIONDATE REAL,
                ZORDERINDEX INTEGER DEFAULT 0
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
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO ZNOTE (
                ZIDENTIFIER, ZFOLDERID, ZTITLE, ZCONTENT, 
                ZCREATIONDATE, ZMODIFICATIONDATE,
                ZISFAVORITE, ZISDELETED
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        ''', (note_id, folder_id, title, content, cocoa_time, cocoa_time))
        
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
                   content: Optional[str] = None):
        """更新笔记"""
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
            cursor.execute('''
                UPDATE ZNOTE SET ZCONTENT = ? WHERE ZIDENTIFIER = ?
            ''', (content, note_id))
            
        # 更新修改时间
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        cursor.execute('''
            UPDATE ZNOTE SET ZMODIFICATIONDATE = ? WHERE ZIDENTIFIER = ?
        ''', (cocoa_time, note_id))
        
        self.conn.commit()
        
    def delete_note(self, note_id: str):
        """删除笔记（移到回收站）"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZISDELETED = 1, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
        ''', (cocoa_time, note_id))
        
        self.conn.commit()
        
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
        """获取所有未删除的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZISDELETED = 0
            ORDER BY ZMODIFICATIONDATE DESC
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
        """获取指定文件夹的笔记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM ZNOTE 
            WHERE ZFOLDERID = ? AND ZISDELETED = 0
            ORDER BY ZMODIFICATIONDATE DESC
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
        
        return {
            'id': row['ZIDENTIFIER'],
            'folder_id': row['ZFOLDERID'],
            'title': row['ZTITLE'] or '无标题',
            'content': row['ZCONTENT'] or '',
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
    
    def create_folder(self, name: str) -> str:
        """创建新文件夹"""
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
                ZIDENTIFIER, ZNAME, ZCREATIONDATE, 
                ZMODIFICATIONDATE, ZORDERINDEX
            ) VALUES (?, ?, ?, ?, ?)
        ''', (folder_id, name, cocoa_time, cocoa_time, order_index))
        
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
        
    def move_note_to_folder(self, note_id: str, folder_id: Optional[str]):
        """将笔记移动到文件夹"""
        cursor = self.conn.cursor()
        cocoa_time = self._timestamp_to_cocoa(datetime.now())
        
        cursor.execute('''
            UPDATE ZNOTE 
            SET ZFOLDERID = ?, ZMODIFICATIONDATE = ?
            WHERE ZIDENTIFIER = ?
        ''', (folder_id, cocoa_time, note_id))
        
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
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'order_index': row['ZORDERINDEX'],
            '_pk': row['Z_PK'],
            '_cocoa_created': row['ZCREATIONDATE'],
            '_cocoa_modified': row['ZMODIFICATIONDATE']
        }
    
    def __del__(self):
        """析构函数，确保数据库连接关闭"""
        self.close()
