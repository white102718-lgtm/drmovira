package com.adpulse.system.loginlog.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.loginlog.mapper.LoginLogMapper;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.model.LoginLog;
import com.adpulse.system.user.model.UserAccount;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/** 登录日志字段边界和查询条件测试。 */
class LoginLogServiceTest {

    private final LoginLogMapper mapper = mock(LoginLogMapper.class);
    private final LoginLogService service = new LoginLogService(mapper);

    @Test
    void shouldRecordBoundedFailureAuditFields() {
        UserAccount user = new UserAccount();
        user.setId(1L);
        user.setUsername("admin");
        user.setDisplayName("系统管理员");

        service.recordFailure(
                user,
                "admin",
                LoginAuthStage.MFA_VERIFY,
                new BusinessException(ApiCode.MFA_CODE_INVALID, "MFA动态码错误或已过期"),
                "127.0.0.1",
                "agent");

        ArgumentCaptor<LoginLog> captor = ArgumentCaptor.forClass(LoginLog.class);
        verify(mapper).insert(captor.capture());
        LoginLog log = captor.getValue();
        assertThat(log.getUserId()).isEqualTo(1L);
        assertThat(log.getAuthStage()).isEqualTo(3);
        assertThat(log.getLoginResult()).isZero();
        assertThat(log.getFailureCode()).isEqualTo(ApiCode.MFA_CODE_INVALID);
        assertThat(log.getFailureReason()).isEqualTo("MFA动态码错误或已过期");
        assertThat(log.getUserAgent()).isEqualTo("agent");
    }

    @Test
    void shouldRejectReversedTimeRange() {
        LocalDateTime startedAt = LocalDateTime.of(2026, 8, 18, 0, 0);
        LocalDateTime endedAt = startedAt.minusSeconds(1);

        assertThatThrownBy(() -> service.page(null, null, null, null, startedAt, endedAt, 1, 20))
                .isInstanceOf(BusinessException.class)
                .hasMessage("开始时间不能晚于结束时间");

        verify(mapper, never())
                .findPage(any(), any(), any(), any(), any(), any(), anyInt(), anyInt());
    }
}
