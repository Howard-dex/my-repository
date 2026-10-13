import pandas as pd
import polars as pl
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 中文字体
matplotlib.rcParams['axes.unicode_minus'] = False

# 用 Polars 读取 CSV（换成你的真实路径）
pl_df = pl.read_csv(
    r"D:\BaiduNetdiskDownload\UserBehavior.csv",
    has_header=False,
    new_columns=["user_id", "item_id", "category_id", "behavior_type", "timestamp"],
    schema_overrides={
        "user_id": pl.Int32,
        "item_id": pl.Int32,
        "category_id": pl.Int32,
        "timestamp": pl.Int64,
    },
)

# 时间戳格式化（Polars 用 with_columns 生成新列）
pl_df = pl_df.with_columns(
    pl.from_epoch(pl.col("timestamp"), time_unit="s").alias("datetime")
)

# 去掉时间异常的数据
pl_df = pl_df.filter(
    (pl.col("datetime") >= pl.datetime(2017, 11, 25)) &
    (pl.col("datetime") < pl.datetime(2017, 12, 4))
)

# 去重
pl_df = pl_df.unique()

# 转回 Pandas，后面所有代码保持不变（包括你画图、RFM、随机森林）
df = pl_df.to_pandas()
# 查看 behavior_type 是否有异常值
print(df['behavior_type'].value_counts())
# 总 PV、UV
pv = (df['behavior_type'] == 'pv').sum()
uv = df['user_id'].nunique()
print(f'总PV: {pv}, 总UV: {uv}')

# 日均 PV、UV
df['day'] = df['datetime'].dt.date# ====================================
daily = df.groupby('day').agg(
    pv=('behavior_type', lambda x: (x == 'pv').sum()),
    uv=('user_id', 'nunique')
)
print(daily)
# ========== 用 Polars 替代 Pandas 的 pivot_table ==========
# 1. 把当前的 Pandas df 转成 Polars 惰性 DataFrame
pl_df = pl.from_pandas(df).lazy()

# 2. 用 Polars 分组统计（这一步会自动用上你 CPU 的多核）
user_count_pl = (
    pl_df
    .group_by(["user_id", "behavior_type"])
    .agg(pl.len().alias("cnt"))
    .collect()  # 触发实际计算
)

# 3. 转回 Pandas 的透视表格式，让后面的 RFM 和预测代码无缝衔接
user_count = user_count_pl.to_pandas().pivot_table(
    index="user_id", columns="behavior_type", values="cnt", fill_value=0
)
# ==========================================================
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
# ==================== 合并画图 ====================
fig, axes = plt.subplots(2, 1, figsize=(12, 10))

# 画上半部分（一天时段）
hourly.plot(kind='line', ax=axes[0], marker='o')
axes[0].set_title('一天中各时段用户行为分布')
axes[0].set_xlabel('小时')
axes[0].set_ylabel('次数')

# 画下半部分（一周分布）
weekly.plot(kind='bar', ax=axes[1])
axes[1].set_title('一周用户行为分布')

plt.tight_layout()
plt.show()

# ========== 补上这一步：构造 rfm 表 ==========
buy_df = df[df['behavior_type'] == 'buy']

snapshot = pd.Timestamp('2017-12-04')
rfm = buy_df.groupby('user_id').agg(
    R=('datetime', lambda x: (snapshot - x.max()).days),
    F=('datetime', 'count')
)
# 只看购买行为
buy_df = df[df['behavior_type'] == 'buy']

# R：最近一次购买距 2017-12-04 的天数
snapshot = pd.Timestamp('2017-12-04')
rfm = buy_df.groupby('user_id').agg(
    R=('datetime', lambda x: (snapshot - x.max()).days),
    F=('datetime', 'count')
)

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
# ==========================================
# 第 7 步：构造真实特征 + 分类预测
# ==========================================
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score

# ---------- 1. 构造特征表（以用户为粒度） ----------
# 用之前的 user_count（包含每个用户的 pv/fav/cart/buy 次数）
features = user_count[['pv', 'fav', 'cart', 'buy']].copy()

# 衍生特征：加购率、收藏率、点击-购买转化率
features['cart_rate'] = features['cart'] / (features['pv'] + 1)
features['fav_rate'] = features['fav'] / (features['pv'] + 1)
features['cart_fav_ratio'] = (features['cart'] + features['fav']) / (features['pv'] + 1)

# 衍生特征：活跃度（总行为次数）
features['total_actions'] = features['pv'] + features['fav'] + features['cart'] 

# 衍生特征：RFM 中的 R 和 F
# R：最近一次行为距数据集结束时间的天数（越小越活跃）
snapshot_date = df['datetime'].max()  # 用数据里的最大时间做基准
last_action = df.groupby('user_id')['datetime'].max()
features['R'] = (snapshot_date - last_action).dt.days
features['F'] = df.groupby('user_id').size()  # 总行为次数

# ---------- 2. 定义标签（未来是否购买） ----------
# 逻辑：该用户 buy 次数 > 0 则标记为 1，否则为 0
features['label'] = (features['buy'] > 0).astype(int)

# 删掉原始 buy 列，避免标签泄露（不能拿“是否买过”去预测“是否会买”）
X = features.drop(columns=['label'])
y = features['label']

print(f'特征维度：{X.shape}, 正样本比例：{y.mean():.4f}')
# ---------- 3. 划分训练集和测试集 ----------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ---------- 4. 训练随机森林模型 ----------
model = RandomForestClassifier(
    n_estimators=100,      # 100 棵树
    max_depth=6,           # 控制过拟合
    random_state=42,
    class_weight='balanced'  # 正负样本不平衡时自动调整权重
)
model.fit(X_train, y_train)

# ---------- 5. 评估模型 ----------
y_pred = model.predict(X_test)
y_prob = model.predict_proba(X_test)[:, 1]

print('\n===== 分类报告 =====')
print(classification_report(y_test, y_pred))
print(f'AUC 值：{roc_auc_score(y_test, y_prob):.4f}')

# ---------- 6. 特征重要性（看哪些特征对预测最重要） ----------
importance = pd.DataFrame({
    'feature': X.columns,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print('\n===== 特征重要性 Top 10 =====')
print(importance.head(10))
# ========== 把评估结果和特征重要性画成图表 ==========
import matplotlib.pyplot as plt

# 1. 解析分类报告（把文本转成 DataFrame）
from sklearn.metrics import classification_report
report_dict = classification_report(y_test, y_pred, output_dict=True)
report_df = pd.DataFrame(report_dict).transpose()

# 2. 创建一张大画布（1行2列）
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# 左图：分类指标柱状图
# 只取类别 0 和 1 的 precision, recall, f1-score
classes = ['0', '1']
metrics = ['precision', 'recall', 'f1-score']
x = np.arange(len(classes))
width = 0.25

for i, metric in enumerate(metrics):
    values = [report_df.loc[cls, metric] for cls in classes]
    axes[0].bar(x + i * width, values, width, label=metric)

axes[0].set_xticks(x + width)
axes[0].set_xticklabels(['未购买 (0)', '已购买 (1)'])
axes[0].set_ylim(0, 1.1)
axes[0].set_title('分类指标对比（精确率/召回率/F1）')
axes[0].legend()
axes[0].grid(axis='y', alpha=0.3)

# 右图：特征重要性水平条形图
# 取 Top 10 特征
top_features = importance.head(10)
axes[1].barh(range(len(top_features)), top_features['importance'], color='steelblue')
axes[1].set_yticks(range(len(top_features)))
axes[1].set_yticklabels(top_features['feature'])
axes[1].invert_yaxis()  # 重要性最高的在上面
axes[1].set_xlabel('重要性')
axes[1].set_title('特征重要性 Top 10')
axes[1].grid(axis='x', alpha=0.3)

plt.tight_layout()
plt.show()
# =============================================