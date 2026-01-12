#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iCloud同步管理器 - 使用CloudKit API实现笔记同步
模仿macOS备忘录的同步机制
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

# 使用智能CloudKit管理器（自动选择Mock或真实CloudKit）
from cloudkit_manager import create_cloudkit_sync, get_run_mode, print_environment_info


class CloudKitSyncManager:
    """CloudKit同步管理器类"""
    
    def __init__(self, note_manager):
        self.note_manager = note_manager
        self.container_id = "iCloud.com.encnotes.app"
        self.sync_enabled = False
        self.last_sync_time = None
        
        # 配置文件路径
        self.config_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "sync_config.json"
        
        # 使用智能CloudKit管理器（自动选择Mock或真实CloudKit）
        self.backend = None
        try:
            # 打印环境信息（仅在开发模式）
            mode = get_run_mode()
            if mode == 'development':
                print_environment_info()
            
            # 创建CloudKit同步实例（自动选择Mock或真实）
            self.backend = create_cloudkit_sync(note_manager, self.container_id)
            print(f"✓ CloudKit后端初始化成功")
        except Exception as e:
            print(f"✗ CloudKit后端初始化失败: {e}")
            self.backend = None
        
        # 加载配置
        self.load_config()
        
    def load_config(self):
        """加载同步配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.sync_enabled = config.get('sync_enabled', False)
                    self.last_sync_time = config.get('last_sync_time')
            except Exception as e:
                print(f"加载同步配置失败: {e}")
                
    def save_config(self):
        """保存同步配置"""
        try:
            config = {
                'sync_enabled': self.sync_enabled,
                'last_sync_time': self.last_sync_time
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存同步配置失败: {e}")
            
    def enable_sync(self) -> Tuple[bool, str]:
        """启用iCloud同步"""
        try:
            if not self.backend:
                return False, "CloudKit后端未初始化"
            
            def on_enabled(success, message):
                """启用完成回调"""
                if success:
                    self.sync_enabled = True
                    self.save_config()
                    print(f"✓ {message}")
                else:
                    print(f"✗ {message}")
            
            success, message = self.backend.enable_sync(on_enabled)
            if success:
                return True, message
            else:
                return False, message
            
        except Exception as e:
            return False, f"启用同步失败: {e}"
            
    def disable_sync(self) -> Tuple[bool, str]:
        """禁用iCloud同步"""
        if self.backend:
            success, message = self.backend.disable_sync()
            if success:
                self.sync_enabled = False
                self.save_config()
            return success, message
        else:
            self.sync_enabled = False
            self.save_config()
            return True, "iCloud同步已禁用"
        

    def sync_notes(self) -> Tuple[bool, str]:
        """
        同步笔记到iCloud
        使用CloudKit的增量同步机制
        
        Returns:
            (成功标志, 消息)
        """
        if not self.sync_enabled:
            return False, "同步未启用"
            
        try:
            # 获取上次同步时间
            last_sync = self.note_manager.get_sync_metadata('last_sync_timestamp')
            last_sync_cocoa = float(last_sync) if last_sync else 0.0
            
            # 获取需要同步的笔记（修改时间晚于上次同步）
            modified_notes = self.note_manager.get_notes_modified_after(last_sync_cocoa)
            
            if not modified_notes:
                return True, "没有需要同步的笔记"
            
            # 使用CloudKit后端（自动选择Mock或真实）
            if self.backend:
                def on_pushed(success, saved_count, message):
                    """推送完成回调"""
                    if success:
                        # 更新同步时间
                        now = datetime.now()
                        cocoa_time = self.note_manager._timestamp_to_cocoa(now)
                        self.note_manager.set_sync_metadata('last_sync_timestamp', str(cocoa_time))
                        
                        self.last_sync_time = now.isoformat()
                        self.save_config()
                        print(f"✓ {message}")
                    else:
                        print(f"✗ {message}")
                
                return self.backend.push_notes(modified_notes, on_pushed)
            else:
                return False, "CloudKit后端未初始化"
            
        except Exception as e:
            return False, f"同步失败: {e}"
            

            
    def pull_notes(self) -> Tuple[bool, any]:
        """
        从iCloud拉取笔记
        
        Returns:
            (成功标志, 笔记数据或错误消息)
        """
        if not self.sync_enabled:
            return False, "同步未启用"
        
        # 使用CloudKit后端（自动选择Mock或真实）
        if self.backend:
            def on_pulled(success, records, message):
                """拉取完成回调"""
                if success and records:
                    # 合并远程记录
                    merged_count = self.backend.merge_remote_records(records)
                    print(f"✓ 已合并 {merged_count} 条笔记")
                else:
                    print(f"✗ {message}")
            
            return self.backend.pull_notes(on_pulled)
        else:
            return False, "CloudKit后端未初始化"
            

    def auto_sync(self) -> Tuple[bool, str]:
        """
        自动同步（如果启用）
        
        Returns:
            (成功标志, 消息)
        """
        if not self.sync_enabled:
            return False, "同步未启用"
            
        # 检查是否需要同步（距离上次同步超过5分钟）
        if self.last_sync_time:
            try:
                last_sync = datetime.fromisoformat(self.last_sync_time)
                now = datetime.now()
                diff = (now - last_sync).total_seconds()
                
                if diff < 300:  # 5分钟
                    return False, "距离上次同步时间太短"
            except:
                pass
                
        return self.sync_notes()
        

    def get_sync_status(self) -> Dict:
        """
        获取同步状态信息
        
        Returns:
            同步状态字典
        """
        if self.backend:
            # 返回CloudKit后端状态
            status = self.backend.get_sync_status()
            status['last_sync_time'] = self.last_sync_time
            return status
        else:
            # 返回未初始化状态
            return {
                'enabled': self.sync_enabled,
                'last_sync_time': self.last_sync_time,
                'icloud_available': False,
                'sync_method': 'Not Initialized',
                'container_id': self.container_id,
                'cloudkit_available': False
            }
        

    def fetch_changes(self) -> Tuple[bool, str]:
        """
        获取CloudKit的变更
        使用CKFetchRecordZoneChangesOperation
        """
        if not self.sync_enabled:
            return False, "同步未启用"
        
        if not self.backend:
            return False, "CloudKit后端未初始化"
            
        try:
            # 拉取变更
            success, result = self.backend.pull_notes()
            
            if success:
                return True, result
            else:
                return False, result
                
        except Exception as e:
            return False, f"获取变更失败: {e}"
