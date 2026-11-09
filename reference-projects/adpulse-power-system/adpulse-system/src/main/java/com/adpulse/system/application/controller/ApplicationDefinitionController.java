package com.adpulse.system.application.controller;

import com.adpulse.system.application.dto.ApplicationDefinitionSaveRequest;
import com.adpulse.system.application.dto.ApplicationDefinitionView;
import com.adpulse.system.application.service.ApplicationDefinitionService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 申请入口查询与系统管理接口。 */
@RestController
@RequestMapping("/asset-flow-v2/application-definitions")
@Tag(name = "申请管理", description = "申请入口及其审批配置关联管理")
public class ApplicationDefinitionController {
    private final ApplicationDefinitionService service;

    public ApplicationDefinitionController(ApplicationDefinitionService service) {
        this.service = service;
    }

    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<ApplicationDefinitionView>> enabledList() {
        return ApiResponse.success(service.enabledList());
    }

    @GetMapping("/manage")
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    public ApiResponse<List<ApplicationDefinitionView>> managedList(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) Long approvalConfigId) {
        return ApiResponse.success(service.managedList(keyword, status, approvalConfigId));
    }

    @PostMapping
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    @OperationAudit(
            module = "APPLICATION",
            type = OperationType.CREATE,
            name = "新增申请入口",
            targetType = "media_application_definition")
    public ApiResponse<ApplicationDefinitionView> create(
            @Valid @RequestBody ApplicationDefinitionSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    @OperationAudit(
            module = "APPLICATION",
            type = OperationType.UPDATE,
            name = "修改申请入口",
            targetType = "media_application_definition",
            targetIdParameter = "id")
    public ApiResponse<ApplicationDefinitionView> update(
            @PathVariable Long id, @Valid @RequestBody ApplicationDefinitionSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    @OperationAudit(
            module = "APPLICATION",
            type = OperationType.DELETE,
            name = "删除申请入口",
            targetType = "media_application_definition",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
