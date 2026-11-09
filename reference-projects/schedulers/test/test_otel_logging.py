#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import sys
import os

# Add the parent directory to the path so we can import conf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conf import log_conf

# Initialize logging with OpenTelemetry
log_conf.init('test otel')


def test_logging():
    """Test OpenTelemetry logging with complete formatting"""
    logging.info("测试开始 - 包含完整格式的日志")
    logging.warning("这是一个警告消息")
    logging.error("这是一个错误消息")
    logging.debug("这是一个调试消息")
    
    # Test with variables
    task_id = "task_123"
    date = "2025-07-14"
    logging.info(f"任务开始, task_id: {task_id}, date: {date}")
    
    print("日志测试完成")
    
    # 等待日志发送完成
    import time
    print("等待日志发送到OpenTelemetry...")
    time.sleep(3)

if __name__ == "__main__":
    test_logging()