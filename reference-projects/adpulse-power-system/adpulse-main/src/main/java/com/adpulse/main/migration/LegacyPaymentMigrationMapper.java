package com.adpulse.main.migration;

import com.adpulse.main.migration.LegacyPaymentMigrationModels.Candidate;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.ExistingApplication;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.Ledger;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.PaymentDefinition;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.TargetChannel;
import com.adpulse.main.migration.LegacyPaymentMigrationModels.TargetUser;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 旧打款申请迁移的目标库查询、历史申请写入和幂等账本接口。 */
@Mapper
public interface LegacyPaymentMigrationMapper {
    int schemaReady();

    List<TargetUser> migrationUsers();

    List<TargetChannel> activeChannels(@Param("ids") List<Long> ids);

    PaymentDefinition paymentDefinition();

    List<Ledger> ledgers(
            @Param("environment") String environment,
            @Param("sourceUuid") String sourceUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetUuid") String targetUuid,
            @Param("targetSchema") String targetSchema);

    ExistingApplication applicationByNo(@Param("applicationNo") String applicationNo);

    int insertApplication(@Param("candidate") Candidate candidate);

    int insertLog(
            @Param("applicationId") long applicationId,
            @Param("action") String action,
            @Param("actorId") long actorId,
            @Param("actorName") String actorName,
            @Param("remark") String remark,
            @Param("actionData") String actionData,
            @Param("nodeIndex") int nodeIndex,
            @Param("nodeName") String nodeName,
            @Param("createdAt") LocalDateTime createdAt);

    int insertLedger(
            @Param("environment") String environment,
            @Param("sourceUuid") String sourceUuid,
            @Param("sourceSchema") String sourceSchema,
            @Param("targetUuid") String targetUuid,
            @Param("targetSchema") String targetSchema,
            @Param("candidate") Candidate candidate,
            @Param("executionId") long executionId,
            @Param("operatorId") long operatorId);
}
