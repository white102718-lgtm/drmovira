package com.adpulse.system.feishuorg.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ApplicationConfig;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ApplicationConfigSave;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.Preview;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ScheduleSave;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ScheduleView;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncLog;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncRequest;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncSubmission;
import com.adpulse.system.feishuorg.service.FeishuOrganizationJobService;
import com.adpulse.system.feishuorg.service.FeishuOrganizationService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 飞书组织架构同步管理接口。 */
@RestController
@RequestMapping("/feishu/organization")
@Tag(name = "飞书组织同步", description = "预览并手动同步飞书部门和人员")
@PreAuthorize("hasAuthority('system:department:list') and hasAuthority('system:user:list')")
public class FeishuOrganizationController {

    private final FeishuOrganizationService service;
    private final FeishuOrganizationJobService jobs;

    public FeishuOrganizationController(
            FeishuOrganizationService service, FeishuOrganizationJobService jobs) {
        this.service = service;
        this.jobs = jobs;
    }

    /** 查询组织同步共用的飞书应用配置。 */
    @GetMapping("/config")
    public ApiResponse<ApplicationConfig> applicationConfig() {
        return ApiResponse.success(service.applicationConfig());
    }

    /** 保存组织同步共用的飞书应用配置。 */
    @PutMapping("/config")
    @OperationAudit(
            module = "FEISHU_ORGANIZATION",
            type = OperationType.UPDATE,
            name = "保存飞书应用配置",
            targetType = "feishu_app_config")
    public ApiResponse<ApplicationConfig> saveApplicationConfig(
            @Valid @RequestBody ApplicationConfigSave request) {
        return ApiResponse.success(service.saveApplicationConfig(request));
    }

    /** 预览同步差异，不修改部门和人员。 */
    @PostMapping("/preview")
    public ApiResponse<Preview> preview() {
        return ApiResponse.success(jobs.preview());
    }

    /** 查询最近的同步执行记录。 */
    @GetMapping("/logs")
    public ApiResponse<java.util.List<SyncLog>> logs() {
        return ApiResponse.success(service.logs());
    }

    /** 手动执行一次全量组织同步。 */
    @PostMapping("/sync")
    @OperationAudit(
            module = "FEISHU_ORGANIZATION",
            type = OperationType.UPDATE,
            name = "同步飞书组织架构",
            targetType = "sys_department,sys_user")
    public ApiResponse<SyncSubmission> synchronize(@Valid @RequestBody SyncRequest request) {
        return ApiResponse.success(jobs.submit(request));
    }

    /** 查询自动同步计划。 */
    @GetMapping("/schedule")
    public ApiResponse<ScheduleView> schedule() {
        return ApiResponse.success(jobs.schedule());
    }

    /** 保存自动同步计划，配置变更与操作审计同事务提交。 */
    @PutMapping("/schedule")
    @OperationAudit(
            module = "FEISHU_ORGANIZATION",
            type = OperationType.UPDATE,
            name = "保存组织自动同步计划",
            targetType = "sys_feishu_org_schedule")
    public ApiResponse<ScheduleView> saveSchedule(@Valid @RequestBody ScheduleSave request) {
        return ApiResponse.success(jobs.saveSchedule(request));
    }
}
