package com.adpulse.main.safeheron.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/** Safeheron归集管理接口响应。 */
public final class SafeheronViews {
    private SafeheronViews() {}

    /** 通用分页响应。 */
    public record Page<T>(List<T> items, long total, int page, int pageSize) {}

    /** 归集规则。 */
    public record Rule(
            String id,
            String deptId,
            String deptName,
            String collectAccountKey,
            String collectAccountName,
            String coinKey,
            BigDecimal thresholdUsd,
            Integer frequency,
            Integer gasStationEnabled,
            BigDecimal reserveGas,
            BigDecimal maxTxFee,
            String signer,
            Integer status,
            Integer effectiveStatus,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {}

    /** 归集目标钱包。 */
    public record Wallet(String accountKey, String accountName, String teamId) {}

    /** 钱包支持币种。 */
    public record Coin(String coinKey, String coinName) {}

    /** Safeheron团队审批配置。 */
    public record Team(
            String teamId,
            String teamName,
            String approverId,
            String approverName,
            Integer status) {}

    /** 可选审批用户。 */
    public record User(String userId, String userName, String nickName) {}

    /** 部门树节点。 */
    public record Department(String id, String label, List<Department> children) {}

    /** 归集执行记录。 */
    public record CollectionRecord(
            String id,
            String teamId,
            String deptId,
            String deptName,
            String taskId,
            String sourceAccountName,
            String destAccountName,
            String coinKey,
            String coinName,
            BigDecimal amount,
            BigDecimal amountUsd,
            BigDecimal gasFee,
            Integer status,
            String transactionType,
            String approverId,
            String approverName,
            Integer approveResult,
            String txHash,
            String remark,
            LocalDateTime createTime) {}

    /** 当前查询范围内的归集统计。 */
    public record RecordStatistics(
            long todayCount,
            BigDecimal todayAmountUsd,
            BigDecimal todayGas,
            BigDecimal successRate) {}
}
