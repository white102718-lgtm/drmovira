package com.adpulse.main.project.controller;

import com.adpulse.main.project.sync.AgencyLineSheetSyncService;
import com.adpulse.main.project.sync.AgencyLineSyncViews;
import com.adpulse.system.common.api.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 项目代理线 Google Sheet 同步与历史查询接口。 */
@RestController
@RequestMapping("/project/projects/{projectId}/agency-line-sync")
public class AgencyLineSyncController {
    private final AgencyLineSheetSyncService service;

    public AgencyLineSyncController(AgencyLineSheetSyncService service) {
        this.service = service;
    }

    /** 手动执行当前项目的代理线同步。 */
    @PostMapping
    public ApiResponse<AgencyLineSyncViews.Batch> synchronize(@PathVariable Long projectId) {
        return ApiResponse.success(service.synchronizeManually(projectId));
    }

    /** 分页查询当前项目同步历史。 */
    @GetMapping("/batches")
    public ApiResponse<AgencyLineSyncViews.Page<AgencyLineSyncViews.Batch>> batches(
            @PathVariable Long projectId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int pageSize) {
        return ApiResponse.success(service.batches(projectId, page, pageSize));
    }

    /** 分页查询指定同步批次的失败行。 */
    @GetMapping("/batches/{batchId}/failures")
    public ApiResponse<AgencyLineSyncViews.Page<AgencyLineSyncViews.Failure>> failures(
            @PathVariable Long projectId,
            @PathVariable Long batchId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.failures(projectId, batchId, page, pageSize));
    }
}
