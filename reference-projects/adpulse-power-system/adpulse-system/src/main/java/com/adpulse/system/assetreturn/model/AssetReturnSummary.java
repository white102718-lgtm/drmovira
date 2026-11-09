package com.adpulse.system.assetreturn.model;

/**
 * 资产回收处理概览。
 *
 * @param pending 待处理回收数
 * @param completed 已完成回收数
 * @param total 全部回收单数
 */
public record AssetReturnSummary(long pending, long completed, long total) {}
