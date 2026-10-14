# -*- coding: utf-8 -*-
"""
流式数据生成器：循环读 CSV，持续往 Kafka 写
用法: python datagen-stream.py
"""
import json
import time
from datetime import datetime
from kafka import KafkaProducer

KAFKA_SERVERS = ['localhost:9092']
TOPIC = 'user_behavior'
DATA_FILE = 'user_behavior.log'
LOOP_INTERVAL = 0.5


def parse_line(line):
    parts = line.strip().split(',')
    if len(parts) != 5:
        return None
    try:
        user_id, item_id, category_id, behavior, ts = parts
        return json.dumps({
            "user_id": int(user_id),
            "item_id": int(item_id),
            "category_id": int(category_id),
            "behavior": behavior,
            "ts": datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
        }, ensure_ascii=False)
    except (ValueError, OSError):
        return None


def main():
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_SERVERS,
        value_serializer=lambda v: v.encode('utf-8'),
        acks=0,
        linger_ms=10
    )
    print("[INFO] Kafka 连接成功，开始流式写入...")

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        f.readline()
        lines = [l for l in f if l.strip()]

    print(f"[INFO] 共 {len(lines)} 条，循环写入中...")

    i = 0
    while True:
        batch = lines[i:i + 1000]
        for line in batch:
            payload = parse_line(line)
            if payload:
                producer.send(TOPIC, payload)
        producer.flush()
        i += 1000
        if i >= len(lines):
            i = 0
            print(f"[INFO] 一轮写完，重新循环...")

        time.sleep(LOOP_INTERVAL)


if __name__ == '__main__':
    main()