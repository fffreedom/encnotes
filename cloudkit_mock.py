#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mock CloudKit同步实现
用于开发调试，不会崩溃，模拟CloudKit的所有功能
"""

import json
import pickle
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Callable

logger = logging.getLogger(__name__)


class MockCloudKitSync:
    """Mock CloudKit同步管理器（用于开发调试）"""
    
    def __init__(self, note_manager, container_id="iCloud.com.encnotes.app"):
        """初始化Mock CloudKit同步管理器
        
        Args:
            note_manager: 笔记管理器实例
            container_id: CloudKit容器ID
        """
        logger.info(f"📝 初始化MockCloudKitSync (开发模式), container_id={container_id}")
        print("📝 MockCloudKitSync 初始化（开发模式 - 不会崩溃）")
        
        self.note_manager = note_manager
        self.container_id = container_id
        
        # 同步状态
        self.sync_enabled = False
        self.is_syncing = False
        self.account_status = 1  # 模拟账户可用
        
        # Mock数据存储目录
        self.mock_data_dir = Path.home() / "Library" / "Application Support" / "EncNotes" / "MockCloudKit"
        self.mock_data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Mock数据目录: {self.mock_data_dir}")
    
    def check_account_status(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """检查iCloud账户状态（模拟）
        
        Args:
            completion_handler: 完成回调函数 (success: bool, status: int, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("📝 Mock: 检查iCloud账户状态...")
        
        # 模拟账户可用
        status = 1  # 1 = 可用
        message = "iCloud账户可用（模拟）"
        self.account_status = status
        
        logger.info(f"✓ {message}")
        print(f"✓ {message}")
        
        if completion_handler:
            completion_handler(True, status, message)
        
        return True, message
    
    def enable_sync(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """启用同步（模拟）
        
        Args:
            completion_handler: 完成回调函数 (success: bool, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("📝 Mock: 启用iCloud同步...")
        
        def on_status_checked(success, status, message):
            """账户状态检查完成回调"""
            if success:
                self.sync_enabled = True
                logger.info("✓ iCloud同步已启用（模拟）")
                print("✓ iCloud同步已启用（模拟）")
                if completion_handler:
                    completion_handler(True, "iCloud同步已启用（模拟）")
            else:
                if completion_handler:
                    completion_handler(False, message)
        
        return self.check_account_status(on_status_checked)
    
    def push_notes(self, notes: List[Dict], completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """推送笔记到CloudKit（模拟）
        
        Args:
            notes: 笔记列表
            completion_handler: 完成回调函数 (success: bool, saved_count: int, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info(f"📝 Mock: 推送笔记，数量: {len(notes) if notes else 0}")
        
        if not self.sync_enabled:
            logger.warning("同步未启用")
            return False, "同步未启用"
        
        if self.is_syncing:
            logger.warning("正在同步中")
            return False, "正在同步中..."
        
        if not notes:
            logger.info("没有需要同步的笔记")
            return True, "没有需要同步的笔记"
        
        try:
            self.is_syncing = True
            
            # 保存到Mock存储
            saved_count = 0
            saved_records = []
            
            for note in notes:
                try:
                    note_id = note.get('id')
                    if not note_id:
                        continue
                    
                    # 生成Mock记录ID
                    record_id = f"MockRecord-{note_id}"
                    change_tag = self._generate_change_tag()
                    
                    # 保存到Mock文件
                    record_file = self.mock_data_dir / f"{record_id}.json"
                    mock_record = {
                        'recordID': record_id,
                        'recordChangeTag': change_tag,
                        'identifier': note_id,
                        'title': note.get('title', ''),
                        'content': note.get('content', ''),
                        'creationDate': note.get('_cocoa_created', 0.0),
                        'modificationDate': note.get('_cocoa_modified', 0.0),
                        'isFavorite': note.get('is_favorite', False),
                        'isDeleted': note.get('is_deleted', False),
                        'folderID': note.get('folder_id'),
                        'syncedAt': datetime.now().isoformat()
                    }
                    
                    with open(record_file, 'w', encoding='utf-8') as f:
                        json.dump(mock_record, f, ensure_ascii=False, indent=2)
                    
                    # 更新本地元数据
                    self.note_manager.update_cloudkit_metadata(
                        note_id, record_id, change_tag
                    )
                    
                    saved_records.append(mock_record)
                    saved_count += 1
                    
                    logger.debug(f"Mock保存: {note.get('title', '无标题')}")
                    
                except Exception as e:
                    logger.error(f"Mock保存单条记录失败: {e}")
                    continue
            
            self.is_syncing = False
            
            message = f"成功上传 {saved_count} 条笔记（模拟）"
            logger.info(f"✓ {message}")
            print(f"✓ {message}")
            
            if completion_handler:
                completion_handler(True, saved_count, message)
            
            return True, message
            
        except Exception as e:
            self.is_syncing = False
            error_msg = f"Mock推送异常: {e}"
            logger.error(error_msg, exc_info=True)
            if completion_handler:
                completion_handler(False, 0, error_msg)
            return False, error_msg
    
    def pull_notes(self, completion_handler: Optional[Callable] = None) -> Tuple[bool, str]:
        """从CloudKit拉取笔记（模拟）
        
        Args:
            completion_handler: 完成回调函数 (success: bool, records: List, message: str)
            
        Returns:
            (成功标志, 消息)
        """
        logger.info("📝 Mock: 拉取笔记...")
        
        if not self.sync_enabled:
            return False, "同步未启用"
        
        try:
            # 从Mock存储读取
            records = []
            
            for record_file in self.mock_data_dir.glob("MockRecord-*.json"):
                try:
                    with open(record_file, 'r', encoding='utf-8') as f:
                        record = json.load(f)
                        records.append(record)
                except Exception as e:
                    logger.error(f"读取Mock记录失败 {record_file}: {e}")
                    continue
            
            count = len(records)
            message = f"成功拉取 {count} 条笔记（模拟）"
            logger.info(f"✓ {message}")
            print(f"✓ {message}")
            
            if completion_handler:
                completion_handler(True, records, message)
            
            return True, message
            
        except Exception as e:
            error_msg = f"Mock拉取异常: {e}"
            logger.error(error_msg, exc_info=True)
            if completion_handler:
                completion_handler(False, [], error_msg)
            return False, error_msg
    
    def merge_remote_records(self, records: List[Dict]) -> int:
        """合并远程记录到本地数据库（模拟）
        
        Args:
            records: CloudKit记录列表
            
        Returns:
            合并的笔记数量
        """
        if not records:
            return 0
        
        merged_count = 0
        
        try:
            for record in records:
                try:
                    note_id = record.get('identifier')
                    title = record.get('title', '无标题')
                    content = record.get('content', '')
                    
                    if not note_id:
                        continue
                    
                    remote_modified = record.get('modificationDate', 0.0)
                    
                    # 检查本地是否存在
                    local_note = self.note_manager.get_note(note_id)
                    
                    if not local_note:
                        # 创建新笔记
                        folder_id = record.get('folderID')
                        self.note_manager.create_note(
                            title=title,
                            content=content,
                            folder_id=folder_id
                        )
                        merged_count += 1
                        logger.info(f"Mock创建新笔记: {title}")
                        
                    elif remote_modified > local_note['_cocoa_modified']:
                        # 更新笔记
                        self.note_manager.update_note(
                            note_id,
                            title=title,
                            content=content
                        )
                        merged_count += 1
                        logger.info(f"Mock更新笔记: {title}")
                    
                    # 更新元数据
                    record_id = record.get('recordID', '')
                    change_tag = record.get('recordChangeTag', '')
                    if record_id:
                        self.note_manager.update_cloudkit_metadata(note_id, record_id, change_tag)
                    
                except Exception as e:
                    logger.error(f"Mock合并单条记录失败: {e}")
                    continue
            
            return merged_count
            
        except Exception as e:
            logger.error(f"Mock合并记录失败: {e}")
            return merged_count
    
    def setup_subscription(self, completion_handler: Optional[Callable] = None):
        """设置CloudKit订阅（模拟）
        
        Args:
            completion_handler: 完成回调函数 (success: bool, message: str)
        """
        logger.info("📝 Mock: 设置订阅（模拟）")
        if completion_handler:
            completion_handler(True, "订阅已设置（模拟）")
    
    def disable_sync(self) -> Tuple[bool, str]:
        """禁用同步（模拟）"""
        self.sync_enabled = False
        logger.info("📝 Mock: iCloud同步已禁用")
        return True, "iCloud同步已禁用（模拟）"
    
    def get_sync_status(self) -> Dict:
        """获取同步状态信息（模拟）"""
        return {
            'enabled': self.sync_enabled,
            'is_syncing': self.is_syncing,
            'account_status': self.account_status,
            'account_status_name': '可用（模拟）',
            'cloudkit_available': True,
            'sync_method': 'Mock CloudKit (Development Mode)',
            'container_id': self.container_id,
            'mock_data_dir': str(self.mock_data_dir)
        }
    
    def _generate_change_tag(self) -> str:
        """生成变更标签"""
        import hashlib
        import time
        data = f"{time.time()}{self.container_id}".encode()
        return hashlib.sha256(data).hexdigest()[:16]
