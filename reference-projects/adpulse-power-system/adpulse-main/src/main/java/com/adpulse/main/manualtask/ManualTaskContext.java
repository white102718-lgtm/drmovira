package com.adpulse.main.manualtask;

/** 手动任务运行上下文，统一提供操作人和长文本日志能力。 */
public record ManualTaskContext(Long executionId, Long operatorId, ManualTaskLog log) {}
