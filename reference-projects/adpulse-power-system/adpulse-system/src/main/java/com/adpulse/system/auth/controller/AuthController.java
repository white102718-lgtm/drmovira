package com.adpulse.system.auth.controller;

import com.adpulse.system.auth.dto.FeishuOAuthCallbackRequest;
import com.adpulse.system.auth.dto.FeishuQrInitResponse;
import com.adpulse.system.auth.dto.LoginRequest;
import com.adpulse.system.auth.dto.LoginResponse;
import com.adpulse.system.auth.dto.MfaCodeRequest;
import com.adpulse.system.auth.security.ClientIpResolver;
import com.adpulse.system.auth.service.AuthService;
import com.adpulse.system.auth.service.FeishuOAuthService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.user.dto.UserProfileResponse;
import com.adpulse.system.user.service.UserService;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 系统登录与当前会话接口。 */
@RestController
@RequestMapping("/auth")
@Tag(name = "认证管理", description = "登录、登出和当前会话")
public class AuthController {

    private final AuthService authService;
    private final ClientIpResolver clientIpResolver;
    private final UserService userService;
    private final FeishuOAuthService feishuOAuthService;

    public AuthController(
            AuthService authService,
            ClientIpResolver clientIpResolver,
            UserService userService,
            FeishuOAuthService feishuOAuthService) {
        this.authService = authService;
        this.clientIpResolver = clientIpResolver;
        this.userService = userService;
        this.feishuOAuthService = feishuOAuthService;
    }

    /** 初始化飞书二维码 SDK 所需授权地址。 */
    @PostMapping("/feishu/qr/init")
    @SecurityRequirements
    public ApiResponse<FeishuQrInitResponse> initializeFeishuQr() {
        return ApiResponse.success(feishuOAuthService.initialize());
    }

    /** 使用飞书 OAuth 授权码完成系统登录。 */
    @PostMapping("/feishu/callback")
    @SecurityRequirements
    public ApiResponse<LoginResponse> completeFeishuLogin(
            @Valid @RequestBody FeishuOAuthCallbackRequest request,
            HttpServletRequest servletRequest) {
        return ApiResponse.success(
                feishuOAuthService.complete(
                        request.code(),
                        request.state(),
                        clientIpResolver.resolve(servletRequest),
                        servletRequest.getHeader("User-Agent")));
    }

    /** 用户登录。 */
    @PostMapping("/login")
    @SecurityRequirements
    public ApiResponse<LoginResponse> login(
            @Valid @RequestBody LoginRequest request, HttpServletRequest servletRequest) {
        return ApiResponse.success(
                authService.login(
                        request,
                        clientIpResolver.resolve(servletRequest),
                        servletRequest.getHeader("User-Agent")));
    }

    /** 验证首次绑定的MFA动态码，绑定成功后自动登录。 */
    @PostMapping("/mfa/bind")
    @SecurityRequirements
    public ApiResponse<LoginResponse> bindMfa(
            @Valid @RequestBody MfaCodeRequest request, HttpServletRequest servletRequest) {
        return ApiResponse.success(
                authService.bindMfa(
                        request,
                        clientIpResolver.resolve(servletRequest),
                        servletRequest.getHeader("User-Agent")));
    }

    /** 验证已绑定用户的MFA动态码并完成登录。 */
    @PostMapping("/mfa/verify")
    @SecurityRequirements
    public ApiResponse<LoginResponse> verifyMfa(
            @Valid @RequestBody MfaCodeRequest request, HttpServletRequest servletRequest) {
        return ApiResponse.success(
                authService.verifyMfa(
                        request,
                        clientIpResolver.resolve(servletRequest),
                        servletRequest.getHeader("User-Agent")));
    }

    /** 注销当前会话。 */
    @PostMapping("/logout")
    public ApiResponse<Void> logout() {
        authService.logout(SecurityContextHelper.currentUser());
        return ApiResponse.success();
    }

    /** 返回当前会话用户与权限快照。 */
    @GetMapping("/me")
    public ApiResponse<Map<String, Object>> me() {
        CurrentUser user = SecurityContextHelper.currentUser();
        UserProfileResponse profile = userService.currentProfile();
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("userId", profile.userId());
        response.put("username", profile.username());
        response.put("phone", profile.phone());
        response.put("displayName", profile.displayName());
        response.put("englishNickname", profile.englishNickname());
        response.put("realName", profile.realName());
        response.put("email", profile.email());
        response.put("avatarUrl", profile.avatarUrl());
        response.put("department", profile.department());
        response.put("departments", profile.departments());
        response.put("roles", profile.roles());
        response.put(
                "permissions",
                user.authorities().stream().map(authority -> authority.getAuthority()).toList());
        return ApiResponse.success(response);
    }
}
