package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.auth.client.FeishuOAuthClient;
import com.adpulse.system.auth.dto.FeishuQrInitResponse;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.config.FeishuOAuthProperties;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.service.LoginLogService;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** 飞书二维码 state 与授权地址编排测试。 */
class FeishuOAuthServiceTest {

    private final FeishuOAuthClient client = mock(FeishuOAuthClient.class);
    private final FeishuOAuthStateStore stateStore = mock(FeishuOAuthStateStore.class);
    private final AuthService authService = mock(AuthService.class);
    private final LoginLogService loginLogService = mock(LoginLogService.class);

    @Test
    void shouldBuildSdkGotoWithConfiguredRedirectUriAndOneTimeState() {
        when(client.applicationId()).thenReturn("cli_test");
        when(stateStore.create()).thenReturn("state-1");
        when(stateStore.ttlSeconds()).thenReturn(300L);
        FeishuOAuthService service = service("http://localhost:5555/auth/login");

        FeishuQrInitResponse response = service.initialize();

        assertThat(response.expiresInSeconds()).isEqualTo(300L);
        assertThat(response.gotoUrl())
                .contains("client_id=cli_test")
                .contains("response_type=code")
                .contains("state=state-1")
                .contains("redirect_uri=http://localhost:5555/auth/login");
    }

    @Test
    void shouldRejectExpiredStateBeforeExchangingCode() {
        when(stateStore.consume("expired-state")).thenReturn(false);
        FeishuOAuthService service = service("http://localhost:5555/auth/login");

        assertThatThrownBy(
                        () ->
                                service.complete(
                                        "code-1", "expired-state", "127.0.0.1", "test-agent"))
                .isInstanceOf(BusinessException.class)
                .hasMessage("飞书登录状态无效或已过期，请重新扫码");
        verify(loginLogService)
                .recordFailure(
                        org.mockito.ArgumentMatchers.isNull(),
                        org.mockito.ArgumentMatchers.isNull(),
                        org.mockito.ArgumentMatchers.eq(LoginAuthStage.FEISHU_QR),
                        org.mockito.ArgumentMatchers.any(BusinessException.class),
                        org.mockito.ArgumentMatchers.eq("127.0.0.1"),
                        org.mockito.ArgumentMatchers.eq("test-agent"));
    }

    private FeishuOAuthService service(String redirectUri) {
        return new FeishuOAuthService(
                client,
                stateStore,
                new FeishuOAuthProperties(redirectUri, Duration.ofMinutes(5)),
                authService,
                loginLogService);
    }
}
