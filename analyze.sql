-- ============================================
-- Flink SQL: 用户行为实时分析
-- 三个指标: 每小时成交量 / 累计UV / 类目排行
-- ============================================

-- ① Kafka 源表
CREATE TABLE user_behavior (
    user_id BIGINT,
    item_id BIGINT,
    category_id BIGINT,
    behavior STRING,
    ts TIMESTAMP(3),
    proctime AS PROCTIME(),
    WATERMARK FOR ts AS ts - INTERVAL '5' SECOND
) WITH (
    'connector.type' = 'kafka',
    'connector.version' = 'universal',
    'connector.topic' = 'user_behavior',
    'connector.startup-mode' = 'earliest-offset',
    'connector.properties.bootstrap.servers' = 'localhost:9092',
    'format.type' = 'json'
);

-- ② 每小时成交量 → ES
CREATE TABLE buy_cnt_per_hour (
    hour_of_day BIGINT,
    buy_cnt BIGINT
) WITH (
    'connector.type' = 'elasticsearch',
    'connector.version' = '7',
    'connector.hosts' = 'http://localhost:9200',
    'connector.index' = 'buy_cnt_per_hour',
    'connector.document-type' = 'user_behavior',
    'connector.bulk-flush.max-actions' = '1',
    'update-mode' = 'append',
    'format.type' = 'json'
);

INSERT INTO buy_cnt_per_hour
SELECT HOUR(TUMBLE_START(ts, INTERVAL '1' HOUR)), COUNT(*)
FROM user_behavior
WHERE behavior = 'buy'
GROUP BY TUMBLE(ts, INTERVAL '1' HOUR);

-- ③ 累计 UV → ES
CREATE TABLE cumulative_uv (
    time_str STRING,
    uv BIGINT
) WITH (
    'connector.type' = 'elasticsearch',
    'connector.version' = '7',
    'connector.hosts' = 'http://localhost:9200',
    'connector.index' = 'cumulative_uv',
    'connector.document-type' = 'user_behavior',
    'update-mode' = 'upsert',
    'format.type' = 'json'
);

CREATE VIEW uv_per_10min AS
SELECT
  MAX(SUBSTR(DATE_FORMAT(ts, 'HH:mm'),1,4) || '0') OVER w AS time_str,
  COUNT(DISTINCT user_id) OVER w AS uv
FROM user_behavior
WINDOW w AS (ORDER BY proctime ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW);

INSERT INTO cumulative_uv
SELECT time_str, MAX(uv)
FROM uv_per_10min
GROUP BY time_str;

-- ④ 商品类目销量排行 → ES（需要 MySQL 维表，暂时跳过）
-- 等你有 MySQL 环境再补这段