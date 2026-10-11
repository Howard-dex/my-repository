"""matplotlib 矩阵可视化 —— 稳定可运行版本。

特点：
- 只依赖 matplotlib + numpy，无其他第三方库
- 中文字体做安全回退，缺少字体也不会报错
- 不依赖 matplotlib 的高版本 API，兼容 3.x 全系
- 运行后弹窗显示，不保存图片
"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# ------------------------------------------------------------------ 中文字体安全设置
# 只在系统确实有这些字体时才启用中文，避免字体缺失导致的警告/乱码
from matplotlib import font_manager

_available_fonts = {f.name for f in font_manager.fontManager.ttflist}
for _name in ("Microsoft YaHei", "SimHei", "SimSun"):
    if _name in _available_fonts:
        matplotlib.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
        break
matplotlib.rcParams["axes.unicode_minus"] = False  # 负号正常显示

def plot_matrix(matrix, title="Matrix Heatmap", cmap="viridis", annotate=True):
    """基础热力图：显示二维矩阵，每格标注数值，右侧带颜色条。"""
    matrix = np.asarray(matrix, dtype=float)
    rows, cols = matrix.shape

    fig, ax = plt.subplots(figsize=(1.5 + 0.7 * cols, 1.5 + 0.7 * rows))
    im = ax.imshow(matrix, cmap=cmap, interpolation="nearest")
    fig.colorbar(im, ax=ax, label="value")

    # 刻度（用旧版也支持的写法，先 set 位置再 set 标签）
    ax.set_xticks(np.arange(cols))
    ax.set_yticks(np.arange(rows))
    ax.set_xticklabels([f"c{j + 1}" for j in range(cols)])
    ax.set_yticklabels([f"r{i + 1}" for i in range(rows)])
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.set_title(title)

    # 每格标注数值，按背景深浅自动选黑/白字
    if annotate:
        vmin, vmax = matrix.min(), matrix.max()
        cut = vmin + (vmax - vmin) * 0.6
        for i in range(rows):
            for j in range(cols):
                ax.text(j, i, f"{matrix[i, j]:.2f}",
                        ha="center", va="center", fontsize=9,
                        color="white" if matrix[i, j] < cut else "black")

    # 白色分隔线（不需要额外依赖，用 scatter 的替代：直接画网格）
    ax.set_xticks(np.arange(-0.5, cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.0)
    ax.tick_params(which="minor", length=0)

    fig.tight_layout()
    return fig


def plot_cmap_compare(matrix, cmaps=("viridis", "coolwarm", "Blues", "magma")):
    """同一矩阵用多种配色并排对比。"""
    matrix = np.asarray(matrix, dtype=float)
    fig, axes = plt.subplots(1, len(cmaps), figsize=(3.5 * len(cmaps), 3.5))
    vmin, vmax = matrix.min(), matrix.max()

    for ax, cmap in zip(np.atleast_1d(axes), cmaps):
        im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        ax.set_title(cmap)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(im, ax=ax)

    fig.suptitle("Colormap comparison")
    fig.tight_layout()
    return fig


def plot_correlation(data, labels):
    """相关系数矩阵热力图，范围固定 [-1, 1]。"""
    corr = np.corrcoef(np.asarray(data, dtype=float), rowvar=False)
    n = corr.shape[0]

    fig, ax = plt.subplots(figsize=(1.8 + 0.6 * n, 1.8 + 0.6 * n))
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1, interpolation="nearest")
    fig.colorbar(im, ax=ax, label="correlation")

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_title("Correlation matrix")

    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{corr[i, j]:.2f}", ha="center", va="center", fontsize=9,
                    color="white" if abs(corr[i, j]) > 0.6 else "black")

    fig.tight_layout()
    return fig, corr


def main():
    rng = np.random.default_rng(42)

    # 1) 随机矩阵热力图
    data = rng.random((5, 7)) * 10
    print("矩阵形状:", data.shape)
    print(np.round(data, 2))
    plot_matrix(data, title="Matrix Heatmap", cmap="viridis")

    # 2) 配色对比
    plot_cmap_compare(data)

    # 3) 相关系数矩阵
    samples = rng.normal(size=(200, 4))
    samples[:, 1] = samples[:, 0] * 0.9 + rng.normal(scale=0.3, size=200)
    _, corr = plot_correlation(samples, labels=["A", "B", "C", "D"])
    print("\n相关系数矩阵:\n", np.round(corr, 3))

    print("\n完成，正在打开图形窗口...")
    plt.show()


if __name__ == "__main__":
    main()