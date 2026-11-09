package com.adpulse.system.application.controller;

import com.adpulse.system.application.dto.ApplicationTypeSaveRequest;
import com.adpulse.system.application.dto.ApplicationTypeView;
import com.adpulse.system.application.service.ApplicationTypeService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 资源申请类型查询与维护接口。 */
@RestController
@RequestMapping("/asset-flow-v2/application-types")
@Tag(name = "申请类型管理", description = "维护资源申请中心的类型分组")
public class ApplicationTypeController {
    private final ApplicationTypeService service;

    public ApplicationTypeController(ApplicationTypeService service) {
        this.service = service;
    }

    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<ApplicationTypeView>> enabledList() {
        return ApiResponse.success(service.enabledList());
    }

    @GetMapping("/manage")
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    public ApiResponse<List<ApplicationTypeView>> managedList() {
        return ApiResponse.success(service.managedList());
    }

    @PostMapping
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    @OperationAudit(
            module = "APPLICATION",
            type = OperationType.CREATE,
            name = "新增申请类型",
            targetType = "media_application_type")
    public ApiResponse<ApplicationTypeView> create(
            @Valid @RequestBody ApplicationTypeSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAnyAuthority('system:application:list', 'system:menu:list')")
    @OperationAudit(
            module = "APPLICATION",
            type = OperationType.UPDATE,
            name = "修改申请类型",
            targetType = "media_application_type",
            targetIdParameter = "id")
    public ApiResponse<ApplicationTypeView> update(
            @PathVariable Long id, @Valid @RequestBody ApplicationTypeSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }
}
