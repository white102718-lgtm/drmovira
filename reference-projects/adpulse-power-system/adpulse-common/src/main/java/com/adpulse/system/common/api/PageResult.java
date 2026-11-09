package com.adpulse.system.common.api;

import java.util.List;

/**
 * 通用分页结果。
 *
 * @param items 当前页数据
 * @param total 总记录数
 * @param page 当前页码
 * @param pageSize 每页条数
 * @param <T> 数据类型
 */
public record PageResult<T>(List<T> items, long total, int page, int pageSize) {}
