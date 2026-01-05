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


class NoteManager:
    """笔记管理器类 - 使用SQLite数据库"""
    
    def __init__(self):
        # 数据存储路径 - 模仿macOS备忘录的存储位置
        self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.mathnotes"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / "NoteStore.sqlite"
        self.conn = None
        
        # 初始化加密管理器
        self.encryption_manager = EncryptionManager()
        
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
            # 加密内容
            encrypted_content = self._encrypt_content(content)
            cursor.execute('''
                UPDATE ZNOTE SET ZCONTENT = ? WHERE ZIDENTIFIER = ?
            ''', (encrypted_content, note_id))
            
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
        
        Args:
            content: 明文内容
            
        Returns:
            加密后的内容（如果加密已启用）或原内容
        """
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
    
    def __del__(self):
        """析构函数，确保数据库连接关闭"""
        self.close()
