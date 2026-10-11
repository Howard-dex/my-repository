import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 中文字体
matplotlib.rcParams['axes.unicode_minus'] = False
# ========== 生成模拟数据（替代读取 CSV） ==========
np.random.seed(42)
n = 1000000  # 生成 100 万条数据

start_ts = 1511572800
end_ts = 1512355200

df = pd.DataFrame({
    'user_id': np.random.randint(1, 10000, n),
    'item_id': np.random.randint(1, 5000, n),
    'category_id': np.random.randint(1, 100, n),
    'behavior_type': np.random.choice(
        ['pv', 'buy', 'cart', 'fav'], n, p=[0.9, 0.02, 0.05, 0.03]
    ),
    'timestamp': np.random.randint(start_ts, end_ts, n)
})
# ==================================================

# 去重（对应 Hive 的 group by 去重）
df = df.drop_duplicates()

# 时间戳格式化（对应 from_unixtime）
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')

# 去掉时间异常的数据（对应 where between）
df = df[(df['datetime'] >= '2017-11-25') & (df['datetime'] < '2017-12-04')]

# 查看 behavior_type 是否有异常值
print(df['behavior_type'].value_counts())
# 总 PV、UV
pv = (df['behavior_type'] == 'pv').sum()
uv = df['user_id'].nunique()
print(f'总PV: {pv}, 总UV: {uv}')

# 日均 PV、UV
df['day'] = df['datetime'].dt.date
daily = df.groupby('day').agg(
    pv=('behavior_type', lambda x: (x == 'pv').sum()),
    uv=('user_id', 'nunique')
)
print(daily)

# 每个用户的购物情况（对应 user_behavior_count 表）
user_count = df.pivot_table(
    index='user_id', columns='behavior_type',
    values='item_id', aggfunc='count', fill_value=0
).rename(columns={'pv':'pv','fav':'fav','cart':'cart','buy':'buy'})
user_count = user_count.reindex(columns=['pv','fav','cart','buy'], fill_value=0)

# 复购率
repurchase = (user_count['buy'] > 1).sum() / (user_count['buy'] > 0).sum()
print(f'复购率: {repurchase:.4f}')
total = user_count[['pv','fav','cart','buy']].sum()
pv2favcart = (total['fav'] + total['cart']) / total['pv']
favcart2buy = total['buy'] / (total['fav'] + total['cart'])
pv2buy = total['buy'] / total['pv']

print(f'点击→收藏/加购: {pv2favcart:.4f}')
print(f'收藏/加购→购买: {favcart2buy:.4f}')
print(f'点击→购买(总转化率): {pv2buy:.4f}')
# 一天的活跃时段分布
df['hour'] = df['datetime'].dt.hour
hourly = df.pivot_table(index='hour', columns='behavior_type',
                        values='item_id', aggfunc='count', fill_value=0)

# 一周活跃分布（对应 pmod(datediff(...)-3, 7)）
# 该表达式把周一映射为 0，周日映射为 6
df['weekday'] = (df['datetime'].dt.dayofweek - 0) % 7  # pandas 周一=0，直接对齐
weekly = df[df['datetime'].between('2017-11-27','2017-12-03')].pivot_table(
    index='weekday', columns='behavior_type',
    values='item_id', aggfunc='count', fill_value=0
)
weekly.index = ['周一','周二','周三','周四','周五','周六','周日']

# 只看购买行为
buy_df = df[df['behavior_type'] == 'buy']
# --- 前面算 hourly 和 weekly 的代码全部保留不动 ---
df['hour'] = df['datetime'].dt.hour
hourly = df.pivot_table(index='hour', columns='behavior_type', values='item_id', aggfunc='count', fill_value=0)

# 算 weekly 的代码保留不动
df['weekday'] = (df['datetime'].dt.dayofweek - 0) % 7
weekly = df[df['datetime'].between('2017-11-27','2017-12-03')].pivot_table(
    index='weekday', columns='behavior_type', values='item_id', aggfunc='count', fill_value=0
)
weekly.index = ['周一','周二','周三','周四','周五','周六','周日']

# ========== 把这里原来的两块画图代码，替换成这一整块 ==========
fig, axes = plt.subplots(1, 2, figsize=(16, 6))  # 1行2列

# 左边子图：一天分布
hourly.plot(kind='line', ax=axes[0], marker='o')
axes[0].set_title('一天中各时段用户行为分布')
axes[0].set_xlabel('小时')
axes[0].set_ylabel('次数')

# 右边子图：一周分布
weekly.plot(kind='bar', ax=axes[1])
axes[1].set_title('一周用户行为分布')

plt.tight_layout()
plt.show()  # 这一次只弹出一个窗口，左右各一张图
# ==============================================================
# 打分：按排名分 5 组，前 1/5 打 5 分
rfm['R_score'] = pd.qcut(rfm['R'].rank(method='first'), 5, labels=[5,4,3,2,1]).astype(int)
rfm['F_score'] = pd.qcut(rfm['F'].rank(method='first', ascending=False), 5, labels=[5,4,3,2,1]).astype(int)
rfm['score'] = rfm['R_score'] + rfm['F_score']

print(rfm.sort_values('score', ascending=False).head(20))
# 销量最高的商品
top_items = df.pivot_table(index='item_id', columns='behavior_type',
                           values='user_id', aggfunc='count', fill_value=0)
print(top_items.sort_values('buy', ascending=False).head(10))

# 销量最高的类目
top_cats = df.pivot_table(index='category_id', columns='behavior_type',
                          values='user_id', aggfunc='count', fill_value=0)
print(top_cats.sort_values('buy', ascending=False).head(10))