# -*- coding:utf-8 -*-
import logging
import os
import threading
from logging.config import dictConfig
from pathlib import Path

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

import conf

logs_ = Path(__file__).parent.parent / "logs"
if not logs_.exists():
    logs_.mkdir(parents=True, exist_ok=True)
dictConfig(
    {
        "version": 1,
        # 不要禁用已存在的 logger:dictConfig 默认 disable_existing_loggers=True,
        # 会把 import 顺序早于本模块的 logger 全部静默(典型:包 __init__ 里 eager
        # import 的子模块)。这里关掉,所有模块 logger 都正常生效。
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "[%(asctime)s][%(levelname)s][%(process)s][%(thread)s](%(pathname)s:%(lineno)d)- %(message)s",
            }
        },
        "handlers": {
            "file": {
                "class": "conf.log_handler.MyTimeRotatingFileHandler",
                "filename": logs_ / "log",
                "when": "MIDNIGHT",
                "interval": 1,
                "backupCount": 1,
                "formatter": "default",
                "level": logging.INFO,
                "encoding": "utf-8",
                ".": {
                    "suffix": "%Y-%m-%d.log",
                },
            },
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "level": logging.INFO,
            },
        },
        "root": {"level": logging.DEBUG, "handlers": ["file", "console"]},
    }
)


class LogInitializer:
    """OpenTelemetry日志初始化器 - 使用单例模式防止重复初始化"""

    _lock = threading.Lock()
    _initialized = False

    @classmethod
    def init(cls, name: str):
        with cls._lock:
            if cls._initialized:
                logging.info(f"日志已初始化，跳过重复初始化 (name={name})")
                return
            cls._initialized = True
            logging.info(f"日志初始化 ({name})")
            cls._init_otel_logging(name)

    @staticmethod
    def _init_otel_logging(name: str):
        try:
            otel_endpoint = os.environ["OTEL_ENDPOINT"]
            # 创建资源标识，包含进程和服务信息
            resource = Resource.create(
                {
                    "service.name": name,
                    "deployment.environment": os.environ["DEPLOY_ENV"],
                }
            )
            # 创建日志导出器
            log_exporter = OTLPLogExporter(
                endpoint=otel_endpoint, insecure=True, headers={}  # 使用HTTP而非HTTPS
            )
            # 创建日志处理器（减少批处理延迟）
            log_processor = BatchLogRecordProcessor(
                log_exporter,
                max_queue_size=2048,
                schedule_delay_millis=500,  # 500ms 后发送
                export_timeout_millis=10000,  # 10s 导出超时
                max_export_batch_size=512,
            )
            # 创建日志提供者
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(log_processor)
            # 设置全局日志提供者
            set_logger_provider(logger_provider)

            # 自定义LoggingHandler，添加详细的上下文信息
            class CustomOTELHandler(LoggingHandler):
                @staticmethod
                def _get_attributes(record):
                    attributes = LoggingHandler._get_attributes(record)
                    # code.* 跟 body 前缀里的 路径:行号 重复,不导出
                    for key in ("code.file.path", "code.function.name", "code.line.number"):
                        attributes.pop(key, None)
                    return attributes

                def emit(self, record):
                    if not hasattr(record, "custom"):
                        record.custom = {}
                    record.custom["thread"] = record.thread
                    super().emit(record)

            # 创建自定义OpenTelemetry日志处理器
            otel_handler = CustomOTELHandler(
                level=logging.INFO, logger_provider=logger_provider
            )
            # 保持与现有格式一致的格式化器
            otel_formatter = logging.Formatter(
                "[%(asctime)s][%(levelname)s][%(process)s][%(thread)s](%(pathname)s:%(lineno)d)- %(message)s"
            )
            otel_handler.setFormatter(otel_formatter)
            # 添加到根日志记录器
            root_logger = logging.getLogger()
            root_logger.addHandler(otel_handler)
            logging.info(f"日志初始化完成 ({name})")
        except Exception as e:
            logging.error(f"初始化OpenTelemetry logging 失败: {e}")


def init(name: str = None):
    if name is None:
        return
    if conf.env != conf.Env.PROD:
        return
    LogInitializer.init(name)
