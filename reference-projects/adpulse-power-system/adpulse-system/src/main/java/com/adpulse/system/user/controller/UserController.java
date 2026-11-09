package com.adpulse.system.user.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.user.dto.PasswordResetRequest;
import com.adpulse.system.user.dto.UserAuthorizationRequest;
import com.adpulse.system.user.dto.UserDetail;
import com.adpulse.system.user.dto.UserSaveRequest;
import com.adpulse.system.user.model.UserAccount;
import com.adpulse.system.user.service.UserService;
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

/** 用户及其系统管理关系接口。 */
@RestController
@RequestMapping("/users")
@Tag(name = "用户管理", description = "用户、角色、部门范围及安全信息")
public class UserController {

    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }

    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<PageResult<UserAccount>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status,
            @RequestParam(required = false) Long departmentId,
            @RequestParam(required = false) Long roleId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.page(keyword, status, departmentId, roleId, page, pageSize));
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('system:user:list')")
    public ApiResponse<UserDetail> detail(@PathVariable Long id) {
        return ApiResponse.success(service.detail(id));
    }

    @PostMapping
    @PreAuthorize("hasAuthority('system:user:list')")
    @OperationAudit(
            module = "USER",
            type = OperationType.CREATE,
            name = "新增用户",
            targetType = "sys_user")
    public ApiResponse<UserDetail> create(@Valid @RequestBody UserSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('system:user:list')")
    @OperationAudit(
            module = "USER",
            type = OperationType.UPDATE,
            name = "修改用户",
            targetType = "sys_user",
            targetIdParameter = "id")
    public ApiResponse<UserDetail> update(
            @PathVariable Long id, @Valid @RequestBody UserSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @PutMapping("/{id}/authorization")
    @OperationAudit(
            module = "USER",
            type = OperationType.UPDATE,
            name = "修改飞书用户本地授权",
            targetType = "sys_user",
            targetIdParameter = "id")
    public ApiResponse<UserDetail> updateAuthorization(
            @PathVariable Long id, @Valid @RequestBody UserAuthorizationRequest request) {
        return ApiResponse.success(service.updateAuthorization(id, request));
    }

    @PostMapping("/{id}/password/reset")
    @PreAuthorize("hasAuthority('system:user:list')")
    @OperationAudit(
            module = "USER",
            type = OperationType.RESET_PASSWORD,
            name = "重置用户密码",
            targetType = "sys_user",
            targetIdParameter = "id")
    public ApiResponse<Void> resetPassword(
            @PathVariable Long id, @Valid @RequestBody PasswordResetRequest request) {
        service.resetPassword(id, request.newPassword());
        return ApiResponse.success();
    }

    @PostMapping("/{id}/mfa/reset")
    @PreAuthorize("hasAuthority('system:user:list')")
    @OperationAudit(
            module = "USER",
            type = OperationType.RESET_MFA,
            name = "重置用户MFA",
            targetType = "sys_user",
            targetIdParameter = "id")
    public ApiResponse<Void> resetMfa(@PathVariable Long id) {
        service.resetMfa(id);
        return ApiResponse.success();
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('system:user:list')")
    @OperationAudit(
            module = "USER",
            type = OperationType.DELETE,
            name = "删除用户",
            targetType = "sys_user",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
