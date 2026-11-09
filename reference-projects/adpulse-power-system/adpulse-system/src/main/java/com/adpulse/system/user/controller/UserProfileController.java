package com.adpulse.system.user.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.user.dto.UserPasswordChangeRequest;
import com.adpulse.system.user.dto.UserProfileResponse;
import com.adpulse.system.user.dto.UserProfileUpdateRequest;
import com.adpulse.system.user.service.UserService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 当前登录用户个人资料接口。 */
@RestController
@RequestMapping("/users/me")
@Tag(name = "个人资料", description = "查看和修改当前登录用户资料")
@PreAuthorize("isAuthenticated()")
public class UserProfileController {

    private final UserService service;

    public UserProfileController(UserService service) {
        this.service = service;
    }

    /** 查询当前登录用户个人资料。 */
    @GetMapping
    public ApiResponse<UserProfileResponse> detail() {
        return ApiResponse.success(service.currentProfile());
    }

    /** 修改当前登录用户可自行维护的资料。 */
    @PutMapping
    @OperationAudit(
            module = "USER",
            type = OperationType.UPDATE,
            name = "修改个人资料",
            targetType = "sys_user")
    public ApiResponse<UserProfileResponse> update(
            @Valid @RequestBody UserProfileUpdateRequest request) {
        return ApiResponse.success(service.updateCurrentProfile(request));
    }

    /** 修改当前登录用户密码并注销现有会话。 */
    @PutMapping("/password")
    @OperationAudit(
            module = "USER",
            type = OperationType.UPDATE,
            name = "修改个人密码",
            targetType = "sys_user")
    public ApiResponse<Void> changePassword(@Valid @RequestBody UserPasswordChangeRequest request) {
        service.changeCurrentPassword(request);
        return ApiResponse.success();
    }
}
