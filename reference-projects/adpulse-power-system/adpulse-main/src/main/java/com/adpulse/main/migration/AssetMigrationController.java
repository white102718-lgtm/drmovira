package com.adpulse.main.migration;

import com.adpulse.main.migration.AssetMigrationModels.*;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

/** 老生产渠道账户到新测试或新生产资产台账的一次性迁移接口。 */
@RestController
@RequestMapping("/internal/migrations/channel-account-assets")
@ConditionalOnProperty(name = "adpulse.asset-migration.enabled", havingValue = "true")
public class AssetMigrationController {
    private final AssetMigrationService service;

    public AssetMigrationController(AssetMigrationService service) {
        this.service = service;
    }

    /** 刷新或重新进入页面后找回迁移任务。 */
    @GetMapping("/jobs")
    public ApiResponse<java.util.List<JobView>> jobs() {
        return ApiResponse.success(service.recentJobs());
    }

    /** 确认当前服务环境、实例和映射账本，不允许通过请求切换目标环境。 */
    @GetMapping("/environment")
    public ApiResponse<EnvironmentView> environment() {
        return ApiResponse.success(service.environment());
    }

    /** 创建预检任务，不写资产业务表。 */
    @PostMapping("/plans")
    public ApiResponse<JobView> plan() {
        return ApiResponse.success(JobView.of(service.plan()));
    }

    /** 查询进度、数量与可公开的失败原因。 */
    @GetMapping("/{id}")
    public ApiResponse<JobView> status(@PathVariable String id) {
        return ApiResponse.success(JobView.of(service.status(id)));
    }

    /** 查看分页明细和隔离原因，游标为上页最后一条明细 ID。 */
    @GetMapping("/{id}/items")
    public ApiResponse<Items> items(
            @PathVariable String id,
            @RequestParam(defaultValue = "0") long afterId,
            @RequestParam(required = false) String state) {
        return ApiResponse.success(service.items(id, afterId, state));
    }

    /** 启动固定计划，响应后由后台继续执行。 */
    @PostMapping("/{id}/execute")
    public ApiResponse<JobView> execute(@PathVariable String id, @RequestBody Execute request) {
        return ApiResponse.success(JobView.of(service.execute(id, request)));
    }
}
