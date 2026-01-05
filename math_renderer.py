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
        self.dpi = 72  # 渲染分辨率（72 DPI匹配屏幕显示）
        self.fontsize = 12  # 公式字体大小（略小于正文以匹配行高）
        
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
            total_height = height + depth
            fig.set_size_inches(width / self.dpi, total_height / self.dpi)
            
            # 添加文本（使用center对齐，让公式在图片中居中）
            fig.text(
                0.5, 0.5, f'${latex_code}$',
                fontsize=self.fontsize,
                verticalalignment='bottom',
                horizontalalignment='center'
            )
            
            # 保存到内存
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format='png',
                dpi=self.dpi,
                bbox_inches='tight',
                pad_inches=0.05,
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
        将MathML转换为LaTeX后渲染
        """
        try:
            # 尝试使用lxml解析MathML
            from lxml import etree
            
            # 解析MathML
            root = etree.fromstring(mathml_code.encode('utf-8'))
            
            # 将MathML转换为LaTeX
            latex_code = self._mathml_to_latex(root)
            
            # 使用LaTeX渲染器渲染
            return self.render_latex(latex_code)
            
        except Exception as e:
            print(f"MathML渲染失败: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def _mathml_to_latex(self, element):
        """
        将MathML元素转换为LaTeX代码
        支持常用的MathML标签
        """
        tag = element.tag
        
        # 移除命名空间
        if '}' in tag:
            tag = tag.split('}')[1]
        
        # 处理不同的MathML标签
        if tag == 'math':
            # 根元素，处理子元素
            return ''.join(self._mathml_to_latex(child) for child in element)
        
        elif tag == 'mi':  # 标识符（变量）
            return element.text or ''
        
        elif tag == 'mn':  # 数字
            return element.text or ''
        
        elif tag == 'mo':  # 运算符
            op = element.text or ''
            # 特殊运算符映射
            op_map = {
                '×': r'\times',
                '÷': r'\div',
                '≤': r'\leq',
                '≥': r'\geq',
                '≠': r'\neq',
                '∞': r'\infty',
                '∑': r'\sum',
                '∏': r'\prod',
                '∫': r'\int',
            }
            return op_map.get(op, op)
        
        elif tag == 'mfrac':  # 分数
            if len(element) >= 2:
                numerator = self._mathml_to_latex(element[0])
                denominator = self._mathml_to_latex(element[1])
                return rf'\frac{{{numerator}}}{{{denominator}}}'
            return ''
        
        elif tag == 'msqrt':  # 平方根
            content = ''.join(self._mathml_to_latex(child) for child in element)
            return rf'\sqrt{{{content}}}'
        
        elif tag == 'mroot':  # n次根
            if len(element) >= 2:
                base = self._mathml_to_latex(element[0])
                index = self._mathml_to_latex(element[1])
                return rf'\sqrt[{index}]{{{base}}}'
            return ''
        
        elif tag == 'msup':  # 上标
            if len(element) >= 2:
                base = self._mathml_to_latex(element[0])
                superscript = self._mathml_to_latex(element[1])
                return rf'{base}^{{{superscript}}}'
            return ''
        
        elif tag == 'msub':  # 下标
            if len(element) >= 2:
                base = self._mathml_to_latex(element[0])
                subscript = self._mathml_to_latex(element[1])
                return rf'{base}_{{{subscript}}}'
            return ''
        
        elif tag == 'msubsup':  # 上下标
            if len(element) >= 3:
                base = self._mathml_to_latex(element[0])
                subscript = self._mathml_to_latex(element[1])
                superscript = self._mathml_to_latex(element[2])
                return rf'{base}_{{{subscript}}}^{{{superscript}}}'
            return ''
        
        elif tag == 'mrow':  # 行（组合元素）
            return ''.join(self._mathml_to_latex(child) for child in element)
        
        elif tag == 'mtext':  # 文本
            return rf'\text{{{element.text or ""}}}'
        
        elif tag == 'mspace':  # 空格
            return r'\,'
        
        elif tag == 'mfenced':  # 括号
            open_char = element.get('open', '(')
            close_char = element.get('close', ')')
            content = ''.join(self._mathml_to_latex(child) for child in element)
            
            # LaTeX括号映射
            bracket_map = {
                '(': r'\left(',
                ')': r'\right)',
                '[': r'\left[',
                ']': r'\right]',
                '{': r'\left\{',
                '}': r'\right\}',
                '|': r'\left|',
            }
            
            left = bracket_map.get(open_char, open_char)
            right = bracket_map.get(close_char, close_char)
            return f'{left}{content}{right}'
        
        elif tag == 'mtable':  # 矩阵/表格
            rows = []
            for row in element:
                if row.tag.endswith('mtr'):
                    cells = []
                    for cell in row:
                        if cell.tag.endswith('mtd'):
                            cells.append(self._mathml_to_latex(cell))
                    rows.append(' & '.join(cells))
            return r'\begin{matrix}' + r'\\'.join(rows) + r'\end{matrix}'
        
        elif tag == 'munderover':  # 上下限（如求和）
            if len(element) >= 3:
                base = self._mathml_to_latex(element[0])
                under = self._mathml_to_latex(element[1])
                over = self._mathml_to_latex(element[2])
                return rf'{base}_{{{under}}}^{{{over}}}'
            return ''
        
        elif tag == 'munder':  # 下限
            if len(element) >= 2:
                base = self._mathml_to_latex(element[0])
                under = self._mathml_to_latex(element[1])
                return rf'{base}_{{{under}}}'
            return ''
        
        elif tag == 'mover':  # 上限
            if len(element) >= 2:
                base = self._mathml_to_latex(element[0])
                over = self._mathml_to_latex(element[1])
                # 检查是否是帽子、波浪线等
                over_text = element[1].text or ''
                if over_text == '¯':
                    return rf'\overline{{{base}}}'
                elif over_text == '^':
                    return rf'\hat{{{base}}}'
                elif over_text == '~':
                    return rf'\tilde{{{base}}}'
                else:
                    return rf'{base}^{{{over}}}'
            return ''
        
        else:
            # 未知标签，尝试处理子元素
            return ''.join(self._mathml_to_latex(child) for child in element)
