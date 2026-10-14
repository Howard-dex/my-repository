-- ① Kafka 源表（ts 用 STRING，无 WATERMARK）
CREATE TABLE user_behavior (
    user_id BIGINT,
    item_id BIGINT,
    category_id BIGINT,
    behavior STRING,
    ts STRING,
    proctime AS PROCTIME()
) WITH (
    'connector.type' = 'kafka',
    'connector.version' = 'universal',
    'connector.topic' = 'user_behavior',
    'connector.startup-mode' = 'earliest-offset',
    'connector.properties.bootstrap.servers' = 'localhost:9092',
    'format.type' = 'json'
);

-- ② ES 结果表
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

-- ③ 实时计算（用 proctime，1 分钟窗口）
INSERT INTO buy_cnt_per_hour
SELECT HOUR(TUMBLE_START(proctime, INTERVAL '1' MINUTE)), COUNT(*)
FROM user_behavior
WHERE behavior = 'buy'
GROUP BY TUMBLE(proctime, INTERVAL '1' MINUTE);