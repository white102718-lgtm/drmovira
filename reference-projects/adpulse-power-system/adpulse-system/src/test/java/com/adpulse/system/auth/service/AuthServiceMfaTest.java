package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.auth.dto.LoginRequest;
import com.adpulse.system.auth.dto.LoginResponse;
import com.adpulse.system.auth.mapper.AuthMapper;
import com.adpulse.system.auth.model.FeishuIdentity;
import com.adpulse.system.auth.model.ServerSession;
import com.adpulse.system.config.SecurityProperties;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.service.LoginLogService;
import com.adpulse.system.user.model.UserAccount;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.crypto.password.PasswordEncoder;

/** 登录MFA分流和正式会话创建时机测试。 */
class AuthServiceMfaTest {

    private final AuthMapper authMapper = mock(AuthMapper.class);
    private final PasswordEncoder passwordEncoder = mock(PasswordEncoder.class);
    private final IpAccessService ipAccessService = mock(IpAccessService.class);
    private final SessionStore sessionStore = mock(SessionStore.class);
    private final JwtService jwtService = mock(JwtService.class);
    private final MfaChallengeStore challengeStore = mock(MfaChallengeStore.class);
    private final MfaSecretCipher secretCipher = mock(MfaSecretCipher.class);
    private final TotpService totpService = mock(TotpService.class);
    private final LoginLogService loginLogService = mock(LoginLogService.class);

    private AuthService service;
    private UserAccount user;

    @BeforeEach
    void setUp() {
        service =
                new AuthService(
                        authMapper,
                        passwordEncoder,
                        ipAccessService,
                        sessionStore,
                        jwtService,
                        new SecurityProperties("jwt-secret", "issuer", Duration.ofHours(8)),
                        challengeStore,
                        secretCipher,
                        totpService,
                        loginLogService);
        user = new UserAccount();
        user.setId(1L);
        user.setUsername("admin");
        user.setPhone("+8613800000000");
        user.setPasswordHash("hash");
        user.setDisplayName("系统管理员");
        user.setEnglishNickname("Admin");
        user.setRealName("张三");
        user.setPrimaryDepartmentId(10L);
        user.setStatus(1);
        when(authMapper.findLoginUser("+8613800000000")).thenReturn(user);
        when(passwordEncoder.matches("password", "hash")).thenReturn(true);
        when(ipAccessService.isAllowed(user, "127.0.0.1")).thenReturn(true);
    }

    @Test
    void shouldRequireBindingWithoutCreatingFormalSession() {
        user.setMfaStatus(0);
        when(totpService.generateSecret()).thenReturn("BASE32SECRET");
        when(secretCipher.encrypt("BASE32SECRET")).thenReturn("ciphertext");
        when(challengeStore.create(any())).thenReturn("challenge-token");
        when(challengeStore.ttlSeconds()).thenReturn(300L);
        when(totpService.buildOtpAuthUri("+8613800000000", "BASE32SECRET"))
                .thenReturn("otpauth://uri");

        LoginResponse response =
                service.login(
                        new LoginRequest("13800000000", "password"), "127.0.0.1", "test-agent");

        assertThat(response.loginStatus()).isEqualTo("MFA_BIND_REQUIRED");
        assertThat(response.challengeToken()).isEqualTo("challenge-token");
        assertThat(response.mfaSecret()).isEqualTo("BASE32SECRET");
        verify(sessionStore, never()).save(any(ServerSession.class));
        verify(authMapper, never()).recordLoginSuccess(anyLong(), any(), any());
        verify(loginLogService, never()).recordSuccess(any(), any(), any(), any(), any());
    }

    @Test
    void shouldCreateFormalSessionWhenMfaIsDisabled() {
        user.setMfaStatus(-1);
        when(authMapper.findPermissionCodes(1L)).thenReturn(List.of("system:user:list"));
        when(authMapper.findPrimaryDepartmentName(10L)).thenReturn("总部");
        when(authMapper.findActiveRoles(1L))
                .thenReturn(List.of(new AuthMapper.UserRoleView(20L, "admin", "管理员")));
        when(jwtService.issue(anyLong(), any())).thenReturn("jwt");

        LoginResponse response =
                service.login(
                        new LoginRequest("13800000000", "password"), "127.0.0.1", "test-agent");

        assertThat(response.loginStatus()).isEqualTo("SUCCESS");
        assertThat(response.accessToken()).isEqualTo("jwt");
        assertThat(response.challengeToken()).isNull();
        assertThat(response.mfaSecret()).isNull();
        verify(challengeStore, never()).create(any());
        ArgumentCaptor<ServerSession> sessionCaptor = ArgumentCaptor.forClass(ServerSession.class);
        verify(sessionStore).save(sessionCaptor.capture());
        ServerSession session = sessionCaptor.getValue();
        assertThat(session.englishNickname()).isEqualTo("Admin");
        assertThat(session.realName()).isEqualTo("张三");
        assertThat(session.departmentId()).isEqualTo(10L);
        assertThat(session.departmentName()).isEqualTo("总部");
        assertThat(session.roleIds()).containsExactly(20L);
        assertThat(session.roleCodes()).containsExactly("admin");
        assertThat(session.roleNames()).containsExactly("管理员");
        verify(authMapper).recordLoginSuccess(anyLong(), any(), any());
        verify(loginLogService)
                .recordSuccess(
                        user, "+8613800000000", LoginAuthStage.PASSWORD, "127.0.0.1", "test-agent");
    }

    @Test
    void shouldExposeSuperAdminIdentityWithoutAssignedRoles() {
        user.setMfaStatus(-1);
        user.setSuperAdmin(true);
        when(authMapper.findPermissionCodes(1L))
                .thenReturn(List.of("system:user:list", "system:menu:list"));
        when(jwtService.issue(anyLong(), any())).thenReturn("jwt");

        service.login(new LoginRequest("13800000000", "password"), "127.0.0.1", "test-agent");

        ArgumentCaptor<ServerSession> captor = ArgumentCaptor.forClass(ServerSession.class);
        verify(sessionStore).save(captor.capture());
        assertThat(captor.getValue().roleCodes()).containsExactly("SUPER_ADMIN");
        assertThat(captor.getValue().roleNames()).containsExactly("超级管理员");
        assertThat(captor.getValue().roleIds()).isEmpty();
    }

    @Test
    void shouldRecordPasswordAuthenticationFailure() {
        user.setMfaStatus(-1);
        when(passwordEncoder.matches("wrong-password", "hash")).thenReturn(false);

        assertThatThrownBy(
                        () ->
                                service.login(
                                        new LoginRequest("13800000000", "wrong-password"),
                                        "127.0.0.1",
                                        "test-agent"))
                .hasMessage("手机号或密码错误");

        verify(loginLogService)
                .recordFailure(
                        eq(user),
                        eq("+8613800000000"),
                        eq(LoginAuthStage.PASSWORD),
                        any(),
                        eq("127.0.0.1"),
                        eq("test-agent"));
    }

    @Test
    void shouldCreateSessionForSyncedFeishuIdentityWithoutLocalMfaChallenge() {
        user.setMfaStatus(1);
        when(authMapper.findFeishuLoginUser("tenant-1", "ou_1", "on_1")).thenReturn(user);
        when(authMapper.findPermissionCodes(1L)).thenReturn(List.of("system:user:list"));
        when(authMapper.findPrimaryDepartmentName(10L)).thenReturn("总部");
        when(authMapper.findActiveRoles(1L)).thenReturn(List.of());
        when(jwtService.issue(anyLong(), any())).thenReturn("jwt");

        LoginResponse response =
                service.loginWithFeishu(
                        new FeishuIdentity("tenant-1", "ou_1", "on_1", "飞书用户"),
                        "127.0.0.1",
                        "test-agent");

        assertThat(response.loginStatus()).isEqualTo("SUCCESS");
        verify(challengeStore, never()).create(any());
        verify(loginLogService)
                .recordSuccess(
                        user, "feishu:ou_1", LoginAuthStage.FEISHU_QR, "127.0.0.1", "test-agent");
    }
}
