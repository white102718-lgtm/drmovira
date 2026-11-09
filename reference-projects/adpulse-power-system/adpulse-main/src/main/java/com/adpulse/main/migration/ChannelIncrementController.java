package com.adpulse.main.migration;

import com.adpulse.main.migration.ChannelIncrementModels.*;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

/** 测试与生产共用的渠道增量迁移接口，目标环境只允许由服务配置决定。 */
@RestController
@RequestMapping("/internal/migrations/channels")
@ConditionalOnProperty(name = "adpulse.asset-migration.enabled", havingValue = "true")
public class ChannelIncrementController {
    private final ChannelIncrementService service;

    public ChannelIncrementController(ChannelIncrementService service) {
        this.service = service;
    }

    /** 生成实时预检计划；不传 ID 时扫描全部尚未映射的来源渠道。 */
    @PostMapping("/plans")
    public ApiResponse<Plan> plan(@RequestBody(required = false) PlanRequest request) {
        return ApiResponse.success(service.plan(request));
    }

    /** 在当前配置环境执行已确认且未发生漂移的计划。 */
    @PostMapping("/execute")
    public ApiResponse<ExecuteResult> execute(@RequestBody ExecuteRequest request) {
        return ApiResponse.success(service.execute(request));
    }
}
