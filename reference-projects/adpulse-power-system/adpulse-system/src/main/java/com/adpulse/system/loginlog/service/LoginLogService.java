package com.adpulse.system.loginlog.service;

import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.loginlog.mapper.LoginLogMapper;
import com.adpulse.system.loginlog.model.LoginAuthStage;
import com.adpulse.system.loginlog.model.LoginLog;
import com.adpulse.system.user.model.UserAccount;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 登录审计日志的独立写入与管理查询服务。 */
@Service
public class LoginLogService {

    private static final int RESULT_FAILURE = 0;
    private static final int RESULT_SUCCESS = 1;

    private final LoginLogMapper mapper;

    public LoginLogService(LoginLogMapper mapper) {
        this.mapper = mapper;
    }

    /** 分页查询登录日志并限制单页最大数量。 */
    public PageResult<LoginLog> page(
            String keyword,
            Integer loginResult,
            Integer authStage,
            String clientIp,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            int page,
            int pageSize) {
        validateFilters(loginResult, authStage, startedAt, endedAt);
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 200);
        return new PageResult<>(
                mapper.findPage(
                        trimToNull(keyword),
                        loginResult,
                        authStage,
                        trimToNull(clientIp),
                        startedAt,
                        endedAt,
                        (safePage - 1) * safeSize,
                        safeSize),
                mapper.count(
                        trimToNull(keyword),
                        loginResult,
                        authStage,
                        trimToNull(clientIp),
                        startedAt,
                        endedAt),
                safePage,
                safeSize);
    }

    /** 在当前认证事务中记录最终登录成功，事务失败时日志同步回滚。 */
    @Transactional
    public void recordSuccess(
            UserAccount user,
            String loginIdentifier,
            LoginAuthStage authStage,
            String clientIp,
            String userAgent) {
        mapper.insert(
                buildLog(
                        user,
                        loginIdentifier,
                        authStage,
                        RESULT_SUCCESS,
                        null,
                        null,
                        clientIp,
                        userAgent));
    }

    /** 使用独立事务记录认证失败，避免业务异常回滚后丢失审计记录。 */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(
            UserAccount user,
            String loginIdentifier,
            LoginAuthStage authStage,
            BusinessException failure,
            String clientIp,
            String userAgent) {
        mapper.insert(
                buildLog(
                        user,
                        loginIdentifier,
                        authStage,
                        RESULT_FAILURE,
                        failure.getCode(),
                        failure.getMessage(),
                        clientIp,
                        userAgent));
    }

    private LoginLog buildLog(
            UserAccount user,
            String loginIdentifier,
            LoginAuthStage authStage,
            int loginResult,
            Integer failureCode,
            String failureReason,
            String clientIp,
            String userAgent) {
        LoginLog log = new LoginLog();
        if (user != null) {
            log.setUserId(user.getId());
            log.setUsername(limit(user.getUsername(), 64));
            log.setDisplayName(limit(user.getDisplayName(), 100));
        }
        log.setLoginIdentifier(limit(trimToNull(loginIdentifier), 128));
        log.setAuthStage(authStage.getCode());
        log.setLoginResult(loginResult);
        log.setFailureCode(failureCode);
        log.setFailureReason(limit(failureReason, 255));
        log.setClientIp(limit(clientIp, 64));
        log.setUserAgent(limit(trimToNull(userAgent), 500));
        log.setLoginAt(LocalDateTime.now());
        return log;
    }

    private void validateFilters(
            Integer loginResult,
            Integer authStage,
            LocalDateTime startedAt,
            LocalDateTime endedAt) {
        if (loginResult != null && loginResult != RESULT_FAILURE && loginResult != RESULT_SUCCESS) {
            throw BusinessException.validation("登录结果只能为0或1");
        }
        if (authStage != null && (authStage < 1 || authStage > 4)) {
            throw BusinessException.validation("认证阶段只能为1、2、3或4");
        }
        if (startedAt != null && endedAt != null && startedAt.isAfter(endedAt)) {
            throw BusinessException.validation("开始时间不能晚于结束时间");
        }
    }

    private String trimToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private String limit(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }
}
