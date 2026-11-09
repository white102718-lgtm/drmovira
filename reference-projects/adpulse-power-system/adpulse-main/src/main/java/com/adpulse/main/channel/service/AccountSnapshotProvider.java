package com.adpulse.main.channel.service;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/** 从账户信息数据源批量读取列表展示快照。 */
public interface AccountSnapshotProvider {

    /** 按账户 ID 批量查询，不存在的账户不返回。 */
    Map<String, AccountSnapshot> findByAccountIds(List<String> accountIds);

    /** Facebook 账户列表展示快照。 */
    record AccountSnapshot(
            String accountId,
            String accountName,
            Integer status,
            LocalDateTime takeTime,
            Integer timezone,
            String bmId,
            BigDecimal balance,
            BigDecimal amountSpent,
            BigDecimal remainingSpendCap,
            String subjectName) {}
}
