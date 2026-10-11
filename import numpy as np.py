import numpy as np
import matplotlib.pyplot as plt

# 生成一些测试数据（随机正态分布）
v = np.random.randn(1000)

# 计算直方图
(n, bins) = np.histogram(v, bins=50, density=True)

# 计算中心点并画图
plt.plot(.5*(bins[1:]+bins[:-1]), n)
plt.title("My First Matplotlib Plot") # 加个标题
plt.show()