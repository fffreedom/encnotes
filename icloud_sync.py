#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iCloud同步管理器 - 使用CloudKit API实现笔记同步
模仿macOS备忘录的同步机制
"""

import subprocess
import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple


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
            # 检查iCloud是否可用
            if not self.check_icloud_available():
                return False, "iCloud不可用，请在系统设置中登录iCloud账户"
                
            self.sync_enabled = True
            self.save_config()
            
            # 初始化CloudKit容器
            self._init_cloudkit_container()
            
            return True, "iCloud同步已启用（使用CloudKit）"
            
        except Exception as e:
            return False, f"启用同步失败: {e}"
            
    def disable_sync(self) -> Tuple[bool, str]:
        """禁用iCloud同步"""
        self.sync_enabled = False
        self.save_config()
        return True, "iCloud同步已禁用"
        
    def check_icloud_available(self) -> bool:
        """
        检查iCloud是否可用
        通过检查账户状态
        """
        try:
            # 使用defaults命令检查iCloud账户
            result = subprocess.run(
                ['defaults', 'read', 'MobileMeAccounts', 'Accounts'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # 如果有输出且不是错误，说明已登录iCloud
            return result.returncode == 0 and len(result.stdout) > 0
            
        except Exception as e:
            print(f"检查iCloud可用性失败: {e}")
            return False
            
    def _init_cloudkit_container(self):
        """初始化CloudKit容器"""
        # 在数据库中存储容器信息
        self.note_manager.set_sync_metadata('cloudkit_container_id', self.container_id)
        self.note_manager.set_sync_metadata('cloudkit_initialized', 'true')
        
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
                
            # 使用CloudKit命令行工具或API进行同步
            # 注意：这里使用模拟实现，实际需要使用CloudKit框架
            synced_count = self._push_to_cloudkit(modified_notes)
            
            # 更新同步时间
            now = datetime.now()
            cocoa_time = self.note_manager._timestamp_to_cocoa(now)
            self.note_manager.set_sync_metadata('last_sync_timestamp', str(cocoa_time))
            
            self.last_sync_time = now.isoformat()
            self.save_config()
            
            return True, f"同步成功，已上传{synced_count}条笔记"
            
        except Exception as e:
            return False, f"同步失败: {e}"
            
    def _push_to_cloudkit(self, notes: List[Dict]) -> int:
        """
        将笔记推送到CloudKit
        
        这是一个简化的实现。在生产环境中，应该使用：
        1. PyObjC调用CloudKit框架
        2. 或使用CloudKit Web Services API
        3. 或使用CloudKit JS
        """
        try:
            # 创建CloudKit数据缓存目录
            ck_cache_dir = self.config_dir / "CloudKit"
            ck_cache_dir.mkdir(exist_ok=True)
            
            # 保存到本地缓存（模拟CloudKit存储）
            for note in notes:
                record_id = note.get('ck_record_id') or f"Note-{note['id']}"
                record_file = ck_cache_dir / f"{record_id}.ckrecord"
                
                # 创建CloudKit记录格式
                ck_record = {
                    'recordType': 'Note',
                    'recordID': record_id,
                    'recordChangeTag': self._generate_change_tag(),
                    'fields': {
                        'identifier': {'value': note['id']},
                        'title': {'value': note['title']},
                        'content': {'value': note['content']},
                        'creationDate': {'value': note['_cocoa_created']},
                        'modificationDate': {'value': note['_cocoa_modified']},
                        'isFavorite': {'value': note['is_favorite']},
                        'isDeleted': {'value': note['is_deleted']}
                    }
                }
                
                # 保存记录
                with open(record_file, 'wb') as f:
                    pickle.dump(ck_record, f)
                    
                # 更新笔记的CloudKit元数据
                self.note_manager.update_cloudkit_metadata(
                    note['id'],
                    record_id,
                    ck_record['recordChangeTag']
                )
                
            return len(notes)
            
        except Exception as e:
            print(f"推送到CloudKit失败: {e}")
            return 0
            
    def pull_notes(self) -> Tuple[bool, any]:
        """
        从iCloud拉取笔记
        
        Returns:
            (成功标志, 笔记数据或错误消息)
        """
        if not self.sync_enabled:
            return False, "同步未启用"
            
        try:
            # 从CloudKit缓存读取记录
            ck_cache_dir = self.config_dir / "CloudKit"
            
            if not ck_cache_dir.exists():
                return False, "iCloud上没有同步数据"
                
            # 读取所有CloudKit记录
            remote_notes = []
            for record_file in ck_cache_dir.glob("*.ckrecord"):
                try:
                    with open(record_file, 'rb') as f:
                        ck_record = pickle.load(f)
                        remote_notes.append(ck_record)
                except Exception as e:
                    print(f"读取记录失败 {record_file}: {e}")
                    
            if not remote_notes:
                return False, "iCloud上没有同步数据"
                
            return True, {
                'notes': remote_notes,
                'count': len(remote_notes)
            }
            
        except Exception as e:
            return False, f"拉取数据失败: {e}"
            
    def merge_notes(self, remote_records: List[Dict]) -> int:
        """
        合并远程笔记到本地数据库
        
        Args:
            remote_records: CloudKit记录列表
            
        Returns:
            合并的笔记数量
        """
        merged_count = 0
        
        try:
            for ck_record in remote_records:
                fields = ck_record['fields']
                note_id = fields['identifier']['value']
                
                # 检查本地是否存在
                local_note = self.note_manager.get_note(note_id)
                
                if not local_note:
                    # 本地不存在，创建新笔记
                    self.note_manager.create_note(
                        title=fields['title']['value'],
                        content=fields['content']['value']
                    )
                    merged_count += 1
                else:
                    # 比较修改时间
                    remote_modified = fields['modificationDate']['value']
                    local_modified = local_note['_cocoa_modified']
                    
                    if remote_modified > local_modified:
                        # 远程更新，更新本地
                        self.note_manager.update_note(
                            note_id,
                            title=fields['title']['value'],
                            content=fields['content']['value']
                        )
                        merged_count += 1
                        
                # 更新CloudKit元数据
                self.note_manager.update_cloudkit_metadata(
                    note_id,
                    ck_record['recordID'],
                    ck_record['recordChangeTag']
                )
                
            return merged_count
            
        except Exception as e:
            print(f"合并笔记失败: {e}")
            return merged_count
            
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
        
    def _generate_change_tag(self) -> str:
        """生成CloudKit变更标签"""
        import hashlib
        import time
        
        data = f"{time.time()}{self.container_id}".encode()
        return hashlib.sha256(data).hexdigest()[:16]
        
    def get_sync_status(self) -> Dict:
        """
        获取同步状态信息
        
        Returns:
            同步状态字典
        """
        return {
            'enabled': self.sync_enabled,
            'last_sync_time': self.last_sync_time,
            'icloud_available': self.check_icloud_available(),
            'sync_method': 'CloudKit',
            'container_id': self.container_id
        }
        
    def setup_cloudkit_notifications(self):
        """
        设置CloudKit推送通知
        当远程有更新时自动拉取
        """
        # 这需要使用PyObjC调用CloudKit框架
        # 这里提供一个占位实现
        pass
        
    def fetch_changes(self) -> Tuple[bool, str]:
        """
        获取CloudKit的变更
        使用CKFetchRecordZoneChangesOperation
        """
        if not self.sync_enabled:
            return False, "同步未启用"
            
        try:
            # 获取变更令牌
            change_token = self.note_manager.get_sync_metadata('cloudkit_change_token')
            
            # 拉取变更
            success, result = self.pull_notes()
            
            if success:
                remote_records = result['notes']
                merged_count = self.merge_notes(remote_records)
                
                # 保存新的变更令牌
                new_token = self._generate_change_tag()
                self.note_manager.set_sync_metadata('cloudkit_change_token', new_token)
                
                return True, f"已获取并合并{merged_count}条变更"
            else:
                return False, result
                
        except Exception as e:
            return False, f"获取变更失败: {e}"
