#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数学公式渲染器 - 将LaTeX和MathML转换为图片
"""

import io
import tempfile
import os
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice


class MathRenderer:
    """数学公式渲染器"""
    
    def __init__(self):
        self.dpi = 150  # 渲染分辨率
        
    def render(self, code, formula_type):
        """
        渲染数学公式
        
        Args:
            code: 公式代码
            formula_type: 'latex' 或 'mathml'
            
        Returns:
            QImage对象，如果渲染失败返回None
        """
        if formula_type == 'latex':
            return self.render_latex(code)
        elif formula_type == 'mathml':
            return self.render_mathml(code)
        return None
        
    def render_latex(self, latex_code):
        """
        渲染LaTeX公式
        使用matplotlib渲染LaTeX
        """
        try:
            import matplotlib
            matplotlib.use('Agg')  # 使用非GUI后端
            import matplotlib.pyplot as plt
            from matplotlib import mathtext
            
            # 创建图形
            fig = plt.figure(figsize=(0.01, 0.01))
            fig.patch.set_facecolor('white')
            
            # 渲染LaTeX
            parser = mathtext.MathTextParser("path")
            width, height, depth, _, _ = parser.parse(
                f'${latex_code}$',
                dpi=self.dpi,
                prop=None
            )
            
            # 调整图形大小
            fig.set_size_inches(width / self.dpi, height / self.dpi)
            
            # 添加文本
            fig.text(
                0, 0, f'${latex_code}$',
                fontsize=20,
                verticalalignment='bottom',
                horizontalalignment='left'
            )
            
            # 保存到内存
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format='png',
                dpi=self.dpi,
                bbox_inches='tight',
                pad_inches=0.1,
                facecolor='white',
                edgecolor='none'
            )
            plt.close(fig)
            
            # 转换为QImage
            buf.seek(0)
            image = QImage()
            image.loadFromData(buf.read())
            
            return image
            
        except Exception as e:
            print(f"LaTeX渲染失败: {e}")
            return None
            
    def render_mathml(self, mathml_code):
        """
        渲染MathML公式
        使用简单的方法将MathML转换为图片
        """
        try:
            # 尝试使用lxml解析MathML
            from lxml import etree
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            # 解析MathML
            root = etree.fromstring(mathml_code.encode('utf-8'))
            
            # 简单提取文本内容（实际应用中需要更复杂的转换）
            text = self._extract_mathml_text(root)
            
            # 创建图形
            fig, ax = plt.subplots(figsize=(4, 1))
            ax.axis('off')
            ax.text(
                0.5, 0.5, text,
                fontsize=16,
                ha='center',
                va='center',
                family='serif'
            )
            
            # 保存到内存
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format='png',
                dpi=self.dpi,
                bbox_inches='tight',
                pad_inches=0.1,
                facecolor='white'
            )
            plt.close(fig)
            
            # 转换为QImage
            buf.seek(0)
            image = QImage()
            image.loadFromData(buf.read())
            
            return image
            
        except Exception as e:
            print(f"MathML渲染失败: {e}")
            return None
            
    def _extract_mathml_text(self, element):
        """从MathML元素中提取文本"""
        text_parts = []
        
        # 递归提取文本
        if element.text:
            text_parts.append(element.text)
            
        for child in element:
            child_text = self._extract_mathml_text(child)
            if child_text:
                text_parts.append(child_text)
            if child.tail:
                text_parts.append(child.tail)
                
        return ''.join(text_parts)
