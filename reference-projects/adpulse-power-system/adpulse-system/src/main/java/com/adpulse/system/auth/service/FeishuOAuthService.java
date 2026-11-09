package com.adpulse.system.auth.service;

import com.adpulse.system.auth.client.FeishuOAuthClient;
import com.adpulse.system.auth.dto.FeishuQrInitResponse;
import com.adpulse.system.auth.dto.LoginResponse;
import com.adpulse.system.auth.model.FeishuIdentity;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.config.FeishuOAuthProperties;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.service.LoginLogService;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.util.UriComponentsBuilder;

/** 飞书二维码 OAuth 初始化与回调编排服务。 */
@Service
public class FeishuOAuthService {

    private static final String AUTHORIZE_URL =
            "https://passport.feishu.cn/suite/passport/oauth/authorize";

    private final FeishuOAuthClient client;
    private final FeishuOAuthStateStore stateStore;
    private final FeishuOAuthProperties properties;
    private final AuthService authService;
    private final LoginLogService loginLogService;

    public FeishuOAuthService(
            FeishuOAuthClient client,
            FeishuOAuthStateStore stateStore,
            FeishuOAuthProperties properties,
            AuthService authService,
            LoginLogService loginLogService) {
        this.client = client;
        this.stateStore = stateStore;
        this.properties = properties;
        this.authService = authService;
        this.loginLogService = loginLogService;
    }

    /** 创建二维码 SDK 使用的授权地址和一次性 state。 */
    public FeishuQrInitResponse initialize() {
        if (!StringUtils.hasText(properties.redirectUri())) {
            throw BusinessException.conflict("未配置飞书 OAuth 回调地址");
        }
        String applicationId = client.applicationId();
        String state = stateStore.create();
        String gotoUrl =
                UriComponentsBuilder.fromUriString(AUTHORIZE_URL)
                        .queryParam("client_id", applicationId)
                        .queryParam("redirect_uri", properties.redirectUri())
                        .queryParam("response_type", "code")
                        .queryParam("state", state)
                        .build()
                        .encode()
                        .toUriString();
        return new FeishuQrInitResponse(gotoUrl, stateStore.ttlSeconds());
    }

    /** 消费 state 和授权码，并创建本系统 Redis/JWT 会话。 */
    public LoginResponse complete(String code, String state, String clientIp, String userAgent) {
        if (!stateStore.consume(state)) {
            BusinessException failure =
                    new BusinessException(ApiCode.AUTHENTICATION_FAILED, "飞书登录状态无效或已过期，请重新扫码");
            loginLogService.recordFailure(
                    null, null, LoginAuthStage.FEISHU_QR, failure, clientIp, userAgent);
            throw failure;
        }
        FeishuIdentity identity;
        try {
            identity = client.exchangeCode(code);
        } catch (BusinessException failure) {
            loginLogService.recordFailure(
                    null, null, LoginAuthStage.FEISHU_QR, failure, clientIp, userAgent);
            throw failure;
        }
        return authService.loginWithFeishu(identity, clientIp, userAgent);
    }
}
