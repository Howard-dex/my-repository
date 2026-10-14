# -*- coding: utf-8 -*-
"""
用户行为数据生成器
读取 CSV 数据，并发写入 Kafka
用法: python datagen.py 100
"""

import sys
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from kafka import KafkaProducer


# ============ 配置区 ============
KAFKA_BOOTSTRAP_SERVERS = ['localhost:9092']   # 改成本地 Kafka
TOPIC                   = 'user_behavior'
DATA_FILE               = 'user_behavior.log'    # 你的数据文件名
SEND_BATCH              = 200
# ==============================


def parse_line(line):
    parts = line.strip().split(',')
    if len(parts) != 5:
        return None
    try:
        user_id, item_id, category_id, behavior, ts = parts
        record = {
            "user_id":     int(user_id),
            "item_id":     int(item_id),
            "category_id": int(category_id),
            "behavior":    behavior,
            "ts":          datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
        }
        return json.dumps(record, ensure_ascii=False)
    except (ValueError, OSError):
        return None



def send_worker(lines, worker_id):
    producer = build_producer()
    count = 0
    for line in lines:
        payload = parse_line(line)
        if payload is None:
            continue
        producer.send(TOPIC, payload)
        count += 1
        if count % SEND_BATCH == 0:
            producer.flush()
    producer.flush()
    producer.close()
    return count

def build_producer():
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: v.encode('utf-8'),
                acks=0,
                linger_ms=10,
                batch_size=16384
            )
            print("[INFO] Kafka 连接成功")
            return producer
        except Exception as e:
            print(f"[WARN] Kafka 不可用: {e}，3 秒后重试...")
            time.sleep(3)
def split_data(lines, n):
    avg = max(len(lines) // n, 1)
    chunks = []
    for i in range(n):
        start = i * avg
        end = len(lines) if i == n - 1 else (i + 1) * avg
        if start < len(lines):
            chunks.append(lines[start:end])
    return chunks


def main():
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    print(f"[INFO] 并发数 = {concurrency}")
    print(f"[INFO] 数据文件 = {DATA_FILE}")
    print(f"[INFO] Kafka = {KAFKA_BOOTSTRAP_SERVERS}")

    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            f.readline()   # 跳过表头
            lines = [l for l in f if l.strip()]
    except FileNotFoundError:
        print(f"[ERROR] 找不到文件: {DATA_FILE}")
        sys.exit(1)

    print(f"[INFO] 读入 {len(lines)} 条数据，开始并发写入...")

    chunks = split_data(lines, concurrency)
    total = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(send_worker, c, i) for i, c in enumerate(chunks)]
        for fut in as_completed(futures):
            total += fut.result()

    cost = time.time() - start
    print(f"[DONE] 写入 {total} 条，耗时 {cost:.2f}s，TPS ≈ {total / cost:.0f}")


if __name__ == '__main__':
    main()