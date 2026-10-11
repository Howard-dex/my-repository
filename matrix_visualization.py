"""使用 matplotlib 可视化矩阵的示例。

包含：
1. 热力图（带数值标注 + 颜色条）
2. 多种配色方案对比
3. 自定义坐标轴刻度与标题
"""

import importlib.util
import subprocess
import sys


def _ensure(package, import_name=None):
    """缺少依赖时自动安装，避免 ModuleNotFoundError。"""
    import_name = import_name or package
    if importlib.util.find_spec(import_name) is not None:
        return
    print(f"[setup] package '{package}' not found, installing ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


print(f"[info] python: {sys.executable}")
_ensure("numpy")
_ensure("matplotlib")

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

print(f"[info] matplotlib {matplotlib.__version__} | numpy {np.__version__}")

# 让中文和负号正常显示（仅在系统存在中文字体时启用，避免字体缺失报错）
_available_fonts = {f.name for f in font_manager.fontManager.ttflist}
for _name in ("Microsoft YaHei", "SimHei", "SimSun"):
    if _name in _available_fonts:
        matplotlib.rcParams["font.sans-serif"] = [_name, "DejaVu Sans"]
        break
matplotlib.rcParams["axes.unicode_minus"] = False


def plot_matrix_heatmap(matrix, title="矩阵热力图", cmap="viridis", annotate=True, fmt="{:.2f}"):
    """用 imshow 绘制矩阵热力图。

    参数:
        matrix: 二维数组（numpy array 或嵌套列表）
        title:  图标题
        cmap:   matplotlib 配色方案名称
        annotate: 是否在每个格子上标注数值
        fmt:    数值格式化字符串
    """
    matrix = np.asarray(matrix, dtype=float)
    rows, cols = matrix.shape

    fig, ax = plt.subplots(figsize=(1 + 0.8 * cols, 1 + 0.8 * rows))
    im = ax.imshow(matrix, cmap=cmap, aspect="equal")

    # 颜色条
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="数值大小")

    # 坐标轴刻度
    ax.set_xticks(np.arange(cols))
    ax.set_yticks(np.arange(rows))
    ax.set_xticklabels([f"列{i + 1}" for i in range(cols)])
    ax.set_yticklabels([f"行{i + 1}" for i in range(rows)])
    ax.set_xlabel("列")
    ax.set_ylabel("行")
    ax.set_title(title, pad=12)

    # 数值标注：根据背景明暗自动切换文字颜色
    if annotate:
        threshold = matrix.min() + (matrix.max() - matrix.min()) * 0.6
        for i in range(rows):
            for j in range(cols):
                color = "white" if matrix[i, j] < threshold else "black"
                ax.text(j, i, fmt.format(matrix[i, j]),
                        ha="center", va="center", color=color, fontsize=9)

    # 网格线
    ax.set_xticks(np.arange(cols + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(rows + 1) - 0.5, minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8, alpha=0.6)

    fig.tight_layout()
    return fig, ax


def plot_cmap_comparison(matrix, cmaps=("viridis", "coolwarm", "Blues", "magma")):
    """用多种配色方案并排对比同一矩阵。"""
    matrix = np.asarray(matrix, dtype=float)
    fig, axes = plt.subplots(1, len(cmaps), figsize=(4 * len(cmaps), 4))

    vmin, vmax = matrix.min(), matrix.max()
    for ax, cmap in zip(axes, cmaps):
        im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_title(cmap)
        ax.set_xticks([])
        ax.set_yticks([])
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle("不同配色方案对比", fontsize=14)
    fig.tight_layout()
    return fig, axes


if __name__ == "__main__":
    # 示例矩阵：5x7 的随机数
    rng = np.random.default_rng(42)
    data = rng.random((5, 7)) * 10

    plot_matrix_heatmap(data, title="矩阵热力图示例", cmap="viridis")
    plot_cmap_comparison(data)

    # 也可以直接传入嵌套列表
    # plot_matrix_heatmap([[1, 2], [3, 4]], title="2x2 矩阵")

    plt.show()
