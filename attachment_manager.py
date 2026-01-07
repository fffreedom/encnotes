#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
附件管理器 - 管理笔记附件的加密存储
"""

import os
import shutil
import uuid
import time
import tempfile
import atexit
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from encryption_manager import EncryptionManager
import json
import hashlib


class AttachmentManager:
    """附件管理器类 - 负责附件的加密存储和管理"""
    
    def __init__(self, encryption_manager: EncryptionManager):
        """
        初始化附件管理器
        
        Args:
            encryption_manager: 加密管理器实例
        """
        self.encryption_manager = encryption_manager
        
        # 附件存储路径
        self.data_dir = Path.home() / "Library" / "Group Containers" / "group.com.encnotes"
        self.attachments_dir = self.data_dir / "attachments"
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        
        # 附件元数据文件
        self.metadata_file = self.attachments_dir / "metadata.json"
        self.metadata = self._load_metadata()
        
        # 临时文件管理
        self.temp_files = set()  # 记录本次会话创建的临时文件
        self.temp_dir = Path(tempfile.gettempdir())
        
        # 启动时清理旧的临时文件（第一层防护）
        self._cleanup_old_temp_files()
        
        # 注册退出时清理函数（第三层防护）
        atexit.register(self._cleanup_session_temp_files)
    
    def _cleanup_old_temp_files(self):
        """
        清理所有临时文件（启动时执行）
        清理所有遗留的临时文件，确保启动时是干净状态
        """
        try:
            pattern = "encnotes_temp_*"
            cleaned_count = 0
            
            for file_path in self.temp_dir.glob(pattern):
                try:
                    # 清理所有临时文件，不检查时间
                    file_path.unlink()
                    cleaned_count += 1
                    print(f"[临时文件清理] 已清理: {file_path.name}")
                except Exception as e:
                    print(f"[临时文件清理] 清理失败 {file_path.name}: {e}")
            
            if cleaned_count > 0:
                print(f"[临时文件清理] 启动时共清理 {cleaned_count} 个临时文件")
                
        except Exception as e:
            print(f"[临时文件清理] 清理临时文件失败: {e}")
    
    def _cleanup_session_temp_files(self):
        """
        清理本次会话的临时文件（退出时执行）
        """
        try:
            cleaned_count = 0
            for file_path_str in list(self.temp_files):
                try:
                    file_path = Path(file_path_str)
                    if file_path.exists():
                        file_path.unlink()
                        cleaned_count += 1
                        print(f"[临时文件清理] 已清理会话文件: {file_path.name}")
                except Exception as e:
                    print(f"[临时文件清理] 清理会话文件失败 {file_path.name}: {e}")
            
            self.temp_files.clear()
            
            if cleaned_count > 0:
                print(f"[临时文件清理] 退出时共清理 {cleaned_count} 个临时文件")
                
        except Exception as e:
            print(f"[临时文件清理] 清理会话临时文件失败: {e}")
    
    def _create_temp_file(self, attachment_id: str, original_name: str, file_data: bytes) -> Optional[str]:
        """
        创建临时文件（用于打开附件）
        
        Args:
            attachment_id: 附件ID
            original_name: 原始文件名
            file_data: 文件数据
            
        Returns:
            临时文件路径，失败返回None
        """
        try:
            # 生成临时文件名
            temp_filename = f"encnotes_temp_{attachment_id}_{original_name}"
            temp_path = self.temp_dir / temp_filename
            
            # 如果文件已存在，先删除（避免打开旧版本）
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    print(f"[临时文件] 删除旧临时文件失败: {e}")
            
            # 写入文件数据
            with open(temp_path, 'wb') as f:
                f.write(file_data)
            
            # 记录到会话临时文件列表（第二层防护）
            self.temp_files.add(str(temp_path))
            
            print(f"[临时文件] 已创建: {temp_path.name}")
            return str(temp_path)
            
        except Exception as e:
            print(f"[临时文件] 创建临时文件失败: {e}")
            return None
    
    def manual_cleanup_temp_files(self) -> Tuple[int, str]:
        """
        手动清理所有临时文件（可选的第四层防护）
        可以在应用设置中提供此功能
        
        Returns:
            (清理数量, 消息)
        """
        try:
            pattern = "encnotes_temp_*"
            cleaned_count = 0
            
            for file_path in self.temp_dir.glob(pattern):
                try:
                    file_path.unlink()
                    cleaned_count += 1
                except Exception as e:
                    print(f"[临时文件清理] 手动清理失败 {file_path.name}: {e}")
            
            # 同时清空会话记录
            self.temp_files.clear()
            
            return cleaned_count, f"已清理 {cleaned_count} 个临时文件"
            
        except Exception as e:
            return 0, f"清理失败: {str(e)}"
    
    def _load_metadata(self) -> Dict:
        """加载附件元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载附件元数据失败: {e}")
                return {}
        return {}
    
    def _save_metadata(self):
        """保存附件元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存附件元数据失败: {e}")
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """
        计算文件的SHA256哈希值
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件的SHA256哈希值
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def add_attachment(self, source_path: str, note_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        添加附件 - 复制文件到应用目录并加密
        
        Args:
            source_path: 源文件路径
            note_id: 关联的笔记ID
            
        Returns:
            (成功标志, 消息, 附件ID)
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(source_path):
                return False, "文件不存在", None
            
            # 获取文件信息
            file_name = os.path.basename(source_path)
            file_size = os.path.getsize(source_path)
            file_hash = self._calculate_file_hash(source_path)
            
            # 检查是否已存在相同文件（去重）
            existing_attachment_id = self._find_attachment_by_hash(file_hash)
            if existing_attachment_id:
                # 文件已存在，只需关联到新笔记
                self._add_note_reference(existing_attachment_id, note_id)
                return True, f"附件已存在，已关联到笔记", existing_attachment_id
            
            # 生成唯一的附件ID
            attachment_id = str(uuid.uuid4())
            
            # 创建笔记专属目录
            note_attachments_dir = self.attachments_dir / note_id
            note_attachments_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成加密后的文件名（保留原始扩展名）
            file_ext = Path(file_name).suffix
            encrypted_filename = f"{attachment_id}{file_ext}.enc"
            encrypted_path = note_attachments_dir / encrypted_filename
            
            # 读取文件内容
            with open(source_path, 'rb') as f:
                file_data = f.read()
            
            # 加密文件内容
            if self.encryption_manager.is_unlocked:
                success, encrypted_data = self.encryption_manager.encrypt_data(file_data)
                if not success:
                    return False, "加密文件失败", None
            else:
                # 如果未解锁，直接存储（不加密）
                encrypted_data = file_data
            
            # 保存加密后的文件
            with open(encrypted_path, 'wb') as f:
                f.write(encrypted_data)
            
            # 保存元数据
            self.metadata[attachment_id] = {
                'id': attachment_id,
                'original_name': file_name,
                'encrypted_path': str(encrypted_path),
                'file_size': file_size,
                'file_hash': file_hash,
                'note_ids': [note_id],  # 关联的笔记ID列表
                'created_at': str(Path(source_path).stat().st_ctime),
                'is_encrypted': self.encryption_manager.is_unlocked
            }
            self._save_metadata()
            
            return True, f"附件已加密保存: {file_name}", attachment_id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"添加附件失败: {str(e)}", None
    
    def _find_attachment_by_hash(self, file_hash: str) -> Optional[str]:
        """
        根据文件哈希查找已存在的附件
        
        Args:
            file_hash: 文件哈希值
            
        Returns:
            附件ID，如果不存在则返回None
        """
        for attachment_id, metadata in self.metadata.items():
            if metadata.get('file_hash') == file_hash:
                return attachment_id
        return None
    
    def _add_note_reference(self, attachment_id: str, note_id: str):
        """
        为附件添加笔记引用
        
        Args:
            attachment_id: 附件ID
            note_id: 笔记ID
        """
        if attachment_id in self.metadata:
            note_ids = self.metadata[attachment_id].get('note_ids', [])
            if note_id not in note_ids:
                note_ids.append(note_id)
                self.metadata[attachment_id]['note_ids'] = note_ids
                self._save_metadata()
    
    def get_attachment_path(self, attachment_id: str) -> Optional[str]:
        """
        获取附件的本地路径（用于显示）
        
        Args:
            attachment_id: 附件ID
            
        Returns:
            附件路径，如果不存在则返回None
        """
        if attachment_id in self.metadata:
            return self.metadata[attachment_id].get('encrypted_path')
        return None
    
    def get_attachment_info(self, attachment_id: str) -> Optional[Dict]:
        """
        获取附件信息
        
        Args:
            attachment_id: 附件ID
            
        Returns:
            附件信息字典
        """
        return self.metadata.get(attachment_id)
    
    def open_attachment(self, attachment_id: str) -> Tuple[bool, str, Optional[bytes]]:
        """
        打开附件 - 解密并返回文件内容
        
        Args:
            attachment_id: 附件ID
            
        Returns:
            (成功标志, 消息, 文件内容)
        """
        try:
            if attachment_id not in self.metadata:
                return False, "附件不存在", None
            
            metadata = self.metadata[attachment_id]
            encrypted_path = metadata['encrypted_path']
            
            # 检查文件是否存在
            if not os.path.exists(encrypted_path):
                return False, "附件文件不存在", None
            
            # 读取加密文件
            with open(encrypted_path, 'rb') as f:
                encrypted_data = f.read()
            
            # 解密文件
            if metadata.get('is_encrypted', False):
                if not self.encryption_manager.is_unlocked:
                    return False, "请先解锁加密", None
                
                success, decrypted_data = self.encryption_manager.decrypt_data(encrypted_data)
                if not success:
                    return False, "解密文件失败", None
            else:
                decrypted_data = encrypted_data
            
            return True, "成功", decrypted_data
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"打开附件失败: {str(e)}", None
    
    def open_attachment_with_system(self, attachment_id: str) -> Tuple[bool, str]:
        """
        使用系统默认程序打开附件
        
        Args:
            attachment_id: 附件ID
            
        Returns:
            (成功标志, 消息)
        """
        try:
            # 获取附件信息
            if attachment_id not in self.metadata:
                return False, "附件不存在"
            
            metadata = self.metadata[attachment_id]
            original_name = metadata['original_name']
            
            # 解密并获取文件内容
            success, message, file_data = self.open_attachment(attachment_id)
            if not success:
                return False, message
            
            # 创建临时文件
            temp_path = self._create_temp_file(attachment_id, original_name, file_data)
            if not temp_path:
                return False, "创建临时文件失败"
            
            # 使用系统默认程序打开
            import subprocess
            import platform
            
            system = platform.system()
            try:
                if system == "Darwin":  # macOS
                    subprocess.run(['open', temp_path], check=True)
                elif system == "Windows":
                    os.startfile(temp_path)
                elif system == "Linux":
                    subprocess.run(['xdg-open', temp_path], check=True)
                else:
                    return False, f"不支持的操作系统: {system}"
                
                return True, f"已打开附件: {original_name}"
                
            except subprocess.CalledProcessError as e:
                return False, f"打开文件失败: {e}"
            except Exception as e:
                return False, f"打开文件失败: {e}"
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"打开附件失败: {str(e)}"
    
    def export_attachment(self, attachment_id: str, export_path: str) -> Tuple[bool, str]:
        """
        导出附件到指定路径
        
        Args:
            attachment_id: 附件ID
            export_path: 导出路径
            
        Returns:
            (成功标志, 消息)
        """
        try:
            success, message, file_data = self.open_attachment(attachment_id)
            if not success:
                return False, message
            
            # 保存到指定路径
            with open(export_path, 'wb') as f:
                f.write(file_data)
            
            return True, f"附件已导出到: {export_path}"
            
        except Exception as e:
            return False, f"导出附件失败: {str(e)}"
    
    def delete_attachment(self, attachment_id: str, note_id: str) -> Tuple[bool, str]:
        """
        删除附件（从笔记中移除引用，如果没有其他引用则删除文件）
        
        Args:
            attachment_id: 附件ID
            note_id: 笔记ID
            
        Returns:
            (成功标志, 消息)
        """
        try:
            if attachment_id not in self.metadata:
                return False, "附件不存在"
            
            metadata = self.metadata[attachment_id]
            note_ids = metadata.get('note_ids', [])
            
            # 移除笔记引用
            if note_id in note_ids:
                note_ids.remove(note_id)
                metadata['note_ids'] = note_ids
            
            # 如果没有其他引用，删除文件
            if len(note_ids) == 0:
                encrypted_path = metadata['encrypted_path']
                if os.path.exists(encrypted_path):
                    os.remove(encrypted_path)
                
                # 删除元数据
                del self.metadata[attachment_id]
                self._save_metadata()
                
                return True, "附件已删除"
            else:
                self._save_metadata()
                return True, "已从笔记中移除附件引用"
            
        except Exception as e:
            return False, f"删除附件失败: {str(e)}"
    
    def get_note_attachments(self, note_id: str) -> List[Dict]:
        """
        获取笔记的所有附件
        
        Args:
            note_id: 笔记ID
            
        Returns:
            附件信息列表
        """
        attachments = []
        for attachment_id, metadata in self.metadata.items():
            if note_id in metadata.get('note_ids', []):
                attachments.append(metadata)
        return attachments
    
    def cleanup_orphaned_attachments(self) -> Tuple[int, str]:
        """
        清理孤立的附件（没有关联笔记的附件）
        
        Returns:
            (清理数量, 消息)
        """
        try:
            cleaned_count = 0
            orphaned_ids = []
            
            for attachment_id, metadata in self.metadata.items():
                note_ids = metadata.get('note_ids', [])
                if len(note_ids) == 0:
                    orphaned_ids.append(attachment_id)
            
            for attachment_id in orphaned_ids:
                metadata = self.metadata[attachment_id]
                encrypted_path = metadata['encrypted_path']
                
                # 删除文件
                if os.path.exists(encrypted_path):
                    os.remove(encrypted_path)
                
                # 删除元数据
                del self.metadata[attachment_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                self._save_metadata()
            
            return cleaned_count, f"已清理 {cleaned_count} 个孤立附件"
            
        except Exception as e:
            return 0, f"清理失败: {str(e)}"