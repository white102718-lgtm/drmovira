package com.adpulse.system.loginlog.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.loginlog.model.LoginLog;
import com.adpulse.system.loginlog.service.LoginLogService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 系统登录审计日志查询接口。 */
@RestController
@RequestMapping("/login-logs")
@Tag(name = "登录日志", description = "登录成功和认证失败记录查询")
@PreAuthorize("hasAuthority('system:user:list')")
public class LoginLogController {

    private final LoginLogService service;

    public LoginLogController(LoginLogService service) {
        this.service = service;
    }

    /** 按账号、结果、阶段、IP和时间范围分页查询日志。 */
    @GetMapping
    public ApiResponse<PageResult<LoginLog>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer loginResult,
            @RequestParam(required = false) Integer authStage,
            @RequestParam(required = false) String clientIp,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    LocalDateTime startedAt,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    LocalDateTime endedAt,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.page(
                        keyword,
                        loginResult,
                        authStage,
                        clientIp,
                        startedAt,
                        endedAt,
                        page,
                        pageSize));
    }
}
