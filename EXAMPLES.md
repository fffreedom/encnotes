# 使用示例

## 示例1: 数学公式笔记

### 二次方程求根公式

使用LaTeX插入公式：
```
x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}
```

### 欧拉公式

```
e^{i\pi} + 1 = 0
```

### 积分公式

```
\int_{0}^{\infty} e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
```

## 示例2: 线性代数笔记

### 矩阵乘法

```
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
\begin{pmatrix}
x \\
y
\end{pmatrix}
=
\begin{pmatrix}
ax + by \\
cx + dy
\end{pmatrix}
```

### 行列式

```
\det(A) = \begin{vmatrix}
a & b \\
c & d
\end{vmatrix} = ad - bc
```

## 示例3: 微积分笔记

### 导数定义

```
f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}
```

### 常用导数公式

```
\frac{d}{dx}(x^n) = nx^{n-1}
```

```
\frac{d}{dx}(e^x) = e^x
```

```
\frac{d}{dx}(\sin x) = \cos x
```

## 示例4: 概率论笔记

### 正态分布

```
f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{(x-\mu)^2}{2\sigma^2}}
```

### 期望值

```
E[X] = \sum_{i=1}^{n} x_i p_i
```

### 方差

```
\text{Var}(X) = E[(X - E[X])^2]
```

## 示例5: 物理公式笔记

### 牛顿第二定律

```
F = ma
```

### 能量守恒

```
E = mc^2
```

### 薛定谔方程

```
i\hbar\frac{\partial}{\partial t}\Psi = \hat{H}\Psi
```

## 示例6: 使用MathML

### 分数（MathML）

```xml
<math>
  <mfrac>
    <mi>a</mi>
    <mi>b</mi>
  </mfrac>
</math>
```

### 根号（MathML）

```xml
<math>
  <msqrt>
    <mi>x</mi>
  </msqrt>
</math>
```

### 上标（MathML）

```xml
<math>
  <msup>
    <mi>x</mi>
    <mn>2</mn>
  </msup>
</math>
```

## 提示和技巧

### 1. 快速插入常用公式

在LaTeX对话框中，点击示例按钮可以快速插入常用公式模板。

### 2. 组合使用

你可以在同一篇笔记中混合使用LaTeX和MathML公式。

### 3. 富文本格式

除了数学公式，你还可以使用富文本格式：
- **粗体**
- *斜体*
- 不同的字体大小
- 不同的颜色

### 4. 组织笔记

- 使用收藏功能标记重要笔记
- 定期清理回收站
- 为笔记起一个清晰的标题（第一行）

### 5. 备份数据

定期备份 `~/.mathnotes/notes.json` 文件，以防数据丢失。

## 更多资源

### LaTeX数学符号参考

- 希腊字母: `\alpha, \beta, \gamma, \delta, \theta, \lambda, \mu, \pi, \sigma, \omega`
- 运算符: `\sum, \prod, \int, \lim, \infty`
- 关系符: `\leq, \geq, \neq, \approx, \equiv`
- 箭头: `\rightarrow, \leftarrow, \Rightarrow, \Leftarrow`
- 集合: `\in, \notin, \subset, \cup, \cap, \emptyset`

### 在线LaTeX编辑器

如果需要预览复杂的LaTeX公式，可以使用：
- https://www.latexlive.com/
- https://www.codecogs.com/latex/eqneditor.php

### MathML参考

- https://developer.mozilla.org/zh-CN/docs/Web/MathML

---

**开始创建你的数学笔记吧！** 📐✨
