package com.adpulse.main.migration;

import com.adpulse.main.manualtask.ManualTaskAction;
import com.adpulse.main.manualtask.ManualTaskContext;
import com.adpulse.main.manualtask.ManualTaskDefinition;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** 管理员手动触发的旧系统打款申请迁移任务。 */
@Component
@ConditionalOnProperty(name = "adpulse.asset-migration.enabled", havingValue = "true")
public class LegacyPaymentMigrationTask implements ManualTaskDefinition {
    private final LegacyPaymentMigrationService service;
    private final AssetMigrationProperties properties;

    public LegacyPaymentMigrationTask(
            LegacyPaymentMigrationService service, AssetMigrationProperties properties) {
        this.service = service;
        this.properties = properties;
    }

    @Override
    public String code() {
        return "LEGACY_PAYMENT_MIGRATION";
    }

    @Override
    public String name() {
        return "旧系统打款申请迁移";
    }

    @Override
    public String description() {
        return "预检并迁移旧系统已通过、已拒绝的打款申请；不触发审批待办、通知或文件下载。";
    }

    @Override
    public String requiredAuthority() {
        return "system:manual-task:payment-migration";
    }

    @Override
    public List<ManualTaskAction> actions() {
        return List.of(
                new ManualTaskAction("PREVIEW", "预检", "只读取并核对来源、人员、渠道和幂等账本，不写入申请。", false, null),
                new ManualTaskAction(
                        "APPLY",
                        "执行迁移",
                        "后台将重新预检，并在一个事务中写入当前可安全迁移的历史申请。",
                        true,
                        confirmationText()));
    }

    @Override
    public void execute(ManualTaskContext context) {
        service.preview(context);
    }

    @Override
    public void execute(ManualTaskContext context, String actionCode) {
        switch (actionCode) {
            case "PREVIEW" -> service.preview(context);
            case "APPLY" -> service.apply(context);
            default -> throw new IllegalArgumentException("任务不支持该操作：" + actionCode);
        }
    }

    private String confirmationText() {
        return properties.getTargetEnvironment() == AssetMigrationProperties.TargetEnvironment.TEST
                ? "确认迁移到测试环境"
                : "确认迁移到生产环境";
    }
}
