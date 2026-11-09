package com.adpulse.system.department.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.department.dto.DepartmentSaveRequest;
import com.adpulse.system.department.model.Department;
import com.adpulse.system.department.service.DepartmentService;
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
import org.springframework.web.bind.annotation.RestController;

/** 部门树管理接口。 */
@RestController
@RequestMapping("/departments")
@Tag(name = "部门管理", description = "组织部门树维护")
@PreAuthorize("hasAuthority('system:department:list')")
public class DepartmentController {

    private final DepartmentService service;

    public DepartmentController(DepartmentService service) {
        this.service = service;
    }

    /** 供所有已登录用户读取组织部门选项。 */
    @GetMapping("/tree")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<Department>> tree() {
        return ApiResponse.success(service.tree());
    }

    @PostMapping
    @OperationAudit(
            module = "DEPARTMENT",
            type = OperationType.CREATE,
            name = "新增部门",
            targetType = "sys_department")
    public ApiResponse<Department> create(@Valid @RequestBody DepartmentSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @OperationAudit(
            module = "DEPARTMENT",
            type = OperationType.UPDATE,
            name = "修改部门",
            targetType = "sys_department",
            targetIdParameter = "id")
    public ApiResponse<Department> update(
            @PathVariable Long id, @Valid @RequestBody DepartmentSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @OperationAudit(
            module = "DEPARTMENT",
            type = OperationType.DELETE,
            name = "删除部门",
            targetType = "sys_department",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
