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
        self.dpi = 144  # 渲染分辨率（144 DPI适配高分辨率屏幕，提供清晰显示）
        self.fontsize = 10  # 公式字体大小（适合行内显示，与正文协调）
        
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
    
    def _preprocess_latex(self, latex_code):
        """
        预处理LaTeX代码，将matplotlib不支持的语法转换为支持的语法
        
        Args:
            latex_code: 原始LaTeX代码
            
        Returns:
            处理后的LaTeX代码
        """
        import re
        
        # 1. 转换矩阵环境：\begin{pmatrix}...\end{pmatrix} -> 使用简单的括号和数组
        # matplotlib 不支持 \begin{...}\end{...} 环境，需要转换
        
        # 匹配 pmatrix (带圆括号的矩阵)
        latex_code = re.sub(
            r'\\begin\{pmatrix\}(.*?)\\end\{pmatrix\}',
            lambda m: self._convert_matrix(m.group(1), '(', ')'),
            latex_code,
            flags=re.DOTALL
        )
        
        # 匹配 bmatrix (带方括号的矩阵)
        latex_code = re.sub(
            r'\\begin\{bmatrix\}(.*?)\\end\{bmatrix\}',
            lambda m: self._convert_matrix(m.group(1), '[', ']'),
            latex_code,
            flags=re.DOTALL
        )
        
        # 匹配 matrix (不带括号的矩阵)
        latex_code = re.sub(
            r'\\begin\{matrix\}(.*?)\\end\{matrix\}',
            lambda m: self._convert_matrix(m.group(1), '', ''),
            latex_code,
            flags=re.DOTALL
        )
        
        # 匹配 vmatrix (带竖线的矩阵/行列式)
        latex_code = re.sub(
            r'\\begin\{vmatrix\}(.*?)\\end\{vmatrix\}',
            lambda m: self._convert_matrix(m.group(1), '|', '|'),
            latex_code,
            flags=re.DOTALL
        )
        
        return latex_code
    
    def _convert_matrix(self, content, left_bracket, right_bracket):
        """
        将矩阵内容转换为matplotlib支持的格式
        
        matplotlib的mathtext只支持非常有限的LaTeX命令，不支持矩阵环境。
        我们使用\frac和空格来近似显示矩阵（不完美但能工作）
        
        Args:
            content: 矩阵内容（行用\\分隔，列用&分隔）
            left_bracket: 左括号
            right_bracket: 右括号
            
        Returns:
            转换后的LaTeX代码
        """
        # 分割行（处理 \\ 或 \\\\）
        rows = [row.strip() for row in content.replace('\\\\', '\n').split('\n') if row.strip()]
        
        # 构建矩阵
        matrix_rows = []
        for row in rows:
            # 分割列
            cells = [cell.strip() for cell in row.split('&')]
            matrix_rows.append(cells)
        
        if not matrix_rows:
            return ''
        
        # matplotlib 的 mathtext 只支持：^, _, \frac, \sqrt, \left, \right 等基本命令
        # 不支持：\begin{...}, \atop, \substack 等
        # 
        # 对于矩阵，我们使用一个技巧：用 \frac 的分子和分母来堆叠行
        # 虽然不完美（会有分数线），但至少能显示内容
        
        if len(matrix_rows) == 2 and len(matrix_rows[0]) == 2:
            # 2x2 矩阵：使用 \frac 堆叠两行
            a, b = matrix_rows[0]
            c, d = matrix_rows[1]
            
            # 使用 \frac{上行}{下行} 来堆叠
            # 每行内用空格分隔元素
            # 注意：这会显示分数线，不是理想的矩阵显示
            row1 = f'{a}\\quad{b}'  # \quad 是较大的空格
            row2 = f'{c}\\quad{d}'
            matrix_content = f'\\frac{{{row1}}}{{{row2}}}'
            
            # 添加括号
            if left_bracket == '(':
                return f'\\left({matrix_content}\\right)'
            elif left_bracket == '[':
                return f'\\left[{matrix_content}\\right]'
            elif left_bracket == '|':
                return f'\\left|{matrix_content}\\right|'
            else:
                return matrix_content
        
        elif len(matrix_rows) <= 3 and all(len(row) <= 3 for row in matrix_rows):
            # 其他小矩阵：使用嵌套的 \frac
            # 构建每一行
            row_strs = []
            for row in matrix_rows:
                # 用 \quad 分隔列元素（较大空格）
                row_str = '\\quad'.join(row)
                row_strs.append(row_str)
            
            # 使用嵌套的 \frac 堆叠多行
            if len(row_strs) == 3:
                # 先堆叠前两行，再与第三行堆叠
                matrix_content = f'\\frac{{\\frac{{{row_strs[0]}}}{{{row_strs[1]}}}}}{{{row_strs[2]}}}'
            elif len(row_strs) == 2:
                matrix_content = f'\\frac{{{row_strs[0]}}}{{{row_strs[1]}}}'
            else:
                matrix_content = row_strs[0]
            
            # 添加括号
            if left_bracket == '(':
                return f'\\left({matrix_content}\\right)'
            elif left_bracket == '[':
                return f'\\left[{matrix_content}\\right]'
            elif left_bracket == '|':
                return f'\\left|{matrix_content}\\right|'
            else:
                return matrix_content
        else:
            # 对于更大的矩阵，返回简化表示
            bracket_left = left_bracket if left_bracket else ''
            bracket_right = right_bracket if right_bracket else ''
            return f'{bracket_left}...{bracket_right}'
        
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
            from matplotlib.font_manager import FontProperties
            import re
            
            # 预处理LaTeX代码：将matplotlib不支持的语法转换为支持的语法
            latex_code = self._preprocess_latex(latex_code)
            
            # 创建字体属性对象，指定字体大小
            font_prop = FontProperties(size=self.fontsize)
            
            # 创建图形
            fig = plt.figure(figsize=(0.01, 0.01))
            fig.patch.set_facecolor('white')
            
            # 渲染LaTeX（传入字体属性，让图片尺寸根据字体大小计算）
            parser = mathtext.MathTextParser("path")
            width, height, depth, _, _ = parser.parse(
                f'${latex_code}$',
                dpi=self.dpi,
                prop=font_prop  # **关键修复**：传入字体属性，影响尺寸计算
            )
            
            # 调整图形大小
            total_height = height + depth
            fig_width_inch = width / self.dpi
            fig_height_inch = total_height / self.dpi
            fig.set_size_inches(fig_width_inch, fig_height_inch)
            
            # 添加文本
            # **关键修复**：使用 baseline 对齐，并精确计算垂直位置
            # y_position 应该是基线在图片中的相对位置（从底部算起）
            # depth 是基线以下的高度，total_height 是总高度
            # 所以基线位置 = depth / total_height（从底部算起的比例）
            y_position = depth / total_height if total_height > 0 else 0.5
            
            fig.text(
                0.5, y_position, f'${latex_code}$',
                fontsize=self.fontsize,
                verticalalignment='baseline',  # 使用baseline对齐
                horizontalalignment='center'
            )
            
            # 保存到内存
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format='png',
                dpi=self.dpi,
                bbox_inches=None,  # 不自动裁剪，保持精确尺寸
                pad_inches=0,      # 无额外边距
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
            
            # 预处理：如果有多个<math>标签，合并它们
            mathml_code = self._preprocess_mathml(mathml_code)
            
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
    
    def _preprocess_mathml(self, mathml_code):
        """
        预处理MathML代码
        
        主要处理：
        1. 合并多个<math>标签为一个（当用户组合使用多个快捷按钮时）
        2. 确保有正确的根元素
        
        Args:
            mathml_code: 原始MathML代码
            
        Returns:
            处理后的MathML代码
        """
        import re
        from lxml import etree
        
        # 移除多余的空白
        mathml_code = mathml_code.strip()
        
        # 检查是否有多个<math>标签
        math_tags = re.findall(r'<math[^>]*>.*?</math>', mathml_code, re.DOTALL)
        
        if len(math_tags) > 1:
            # 有多个<math>标签，需要合并
            # 提取每个<math>标签的内容（不包括<math>和</math>）
            contents = []
            for tag in math_tags:
                # 解析每个<math>标签
                try:
                    root = etree.fromstring(tag.encode('utf-8'))
                    # 获取所有子元素的LaTeX表示
                    for child in root:
                        contents.append(etree.tostring(child, encoding='unicode'))
                except Exception as e:
                    # 如果解析失败，尝试直接提取内容
                    content = re.sub(r'</?math[^>]*>', '', tag)
                    if content.strip():
                        contents.append(content)
            
            # 合并所有内容到一个<math>标签中
            if contents:
                merged_content = ''.join(contents)
                mathml_code = f'<math>{merged_content}</math>'
        
        elif not mathml_code.startswith('<math'):
            # 如果没有<math>标签，添加一个
            mathml_code = f'<math>{mathml_code}</math>'
        
        return mathml_code
            
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
