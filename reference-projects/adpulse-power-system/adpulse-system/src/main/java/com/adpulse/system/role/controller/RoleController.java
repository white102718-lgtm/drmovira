package com.adpulse.system.role.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.role.dto.RoleDetail;
import com.adpulse.system.role.dto.RoleSaveRequest;
import com.adpulse.system.role.model.Role;
import com.adpulse.system.role.service.RoleService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
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

/** 角色与菜单权限管理接口。 */
@RestController
@RequestMapping("/roles")
@Tag(name = "角色管理", description = "角色和菜单权限分配")
@PreAuthorize("hasAuthority('system:role:list')")
public class RoleController {

    private final RoleService service;

    public RoleController(RoleService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<PageResult<Role>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.page(keyword, status, page, pageSize));
    }

    @GetMapping("/{id}")
    public ApiResponse<RoleDetail> detail(@PathVariable Long id) {
        return ApiResponse.success(service.detail(id));
    }

    @PostMapping
    @OperationAudit(
            module = "ROLE",
            type = OperationType.CREATE,
            name = "新增角色",
            targetType = "sys_role")
    public ApiResponse<RoleDetail> create(@Valid @RequestBody RoleSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @OperationAudit(
            module = "ROLE",
            type = OperationType.UPDATE,
            name = "修改角色及权限",
            targetType = "sys_role",
            targetIdParameter = "id")
    public ApiResponse<RoleDetail> update(
            @PathVariable Long id, @Valid @RequestBody RoleSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @OperationAudit(
            module = "ROLE",
            type = OperationType.DELETE,
            name = "删除角色",
            targetType = "sys_role",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
