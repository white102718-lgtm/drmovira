package com.adpulse.system.operationlog.service;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.operationlog.audit.OperationLogContext;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.operationlog.mapper.OperationLogMapper;
import com.adpulse.system.operationlog.model.OperationLog;
import java.time.LocalDateTime;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 系统管理操作日志写入与分页查询服务。 */
@Service
public class OperationLogService {

    private static final int RESULT_FAILURE = 0;
    private static final int RESULT_SUCCESS = 1;

    private final OperationLogMapper mapper;

    public OperationLogService(OperationLogMapper mapper) {
        this.mapper = mapper;
    }

    /** 分页查询操作日志并校验枚举和时间范围。 */
    public PageResult<OperationLog> page(
            String keyword,
            String moduleCode,
            String operationType,
            Integer operationResult,
            String clientIp,
            LocalDateTime startedAt,
            LocalDateTime endedAt,
            int page,
            int pageSize) {
        String normalizedType = normalizeOperationType(operationType);
        validateFilters(operationResult, startedAt, endedAt);
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 200);
        return new PageResult<>(
                mapper.findPage(
                        trimToNull(keyword),
                        normalizeCode(moduleCode),
                        normalizedType,
                        operationResult,
                        trimToNull(clientIp),
                        startedAt,
                        endedAt,
                        (safePage - 1) * safeSize,
                        safeSize),
                mapper.count(
                        trimToNull(keyword),
                        normalizeCode(moduleCode),
                        normalizedType,
                        operationResult,
                        trimToNull(clientIp),
                        startedAt,
                        endedAt),
                safePage,
                safeSize);
    }

    /** 在切面开启的业务事务中写入成功日志。 */
    @Transactional
    public void recordSuccess(OperationLogContext context) {
        mapper.insert(buildLog(context, RESULT_SUCCESS, null, null));
    }

    /** 在业务事务回滚后使用独立事务写入失败日志。 */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(OperationLogContext context, Throwable failure) {
        Integer failureCode =
                failure instanceof BusinessException business
                        ? business.getCode()
                        : ApiCode.SYSTEM_ERROR;
        String failureReason =
                failure instanceof BusinessException ? failure.getMessage() : "服务器内部错误";
        mapper.insert(buildLog(context, RESULT_FAILURE, failureCode, failureReason));
    }

    private OperationLog buildLog(
            OperationLogContext context,
            int operationResult,
            Integer failureCode,
            String failureReason) {
        OperationLog log = new OperationLog();
        log.setOperatorUserId(context.operatorUserId());
        log.setOperatorDisplayName(limit(context.operatorDisplayName(), 100));
        log.setModuleCode(limit(context.moduleCode(), 32));
        log.setOperationType(context.operationType().name());
        log.setOperationName(limit(context.operationName(), 100));
        log.setTargetType(limit(context.targetType(), 64));
        log.setTargetId(limit(context.targetId(), 64));
        log.setRequestMethod(limit(context.requestMethod(), 10));
        log.setRequestPath(limit(context.requestPath(), 255));
        log.setClientIp(limit(context.clientIp(), 64));
        log.setUserAgent(limit(trimToNull(context.userAgent()), 500));
        log.setOperationResult(operationResult);
        log.setFailureCode(failureCode);
        log.setFailureReason(limit(failureReason, 255));
        log.setOperatedAt(LocalDateTime.now());
        return log;
    }

    private void validateFilters(
            Integer operationResult, LocalDateTime startedAt, LocalDateTime endedAt) {
        if (operationResult != null
                && operationResult != RESULT_FAILURE
                && operationResult != RESULT_SUCCESS) {
            throw BusinessException.validation("操作结果只能为0或1");
        }
        if (startedAt != null && endedAt != null && startedAt.isAfter(endedAt)) {
            throw BusinessException.validation("开始时间不能晚于结束时间");
        }
    }

    private String normalizeOperationType(String value) {
        String normalized = normalizeCode(value);
        if (normalized == null) {
            return null;
        }
        try {
            return OperationType.valueOf(normalized).name();
        } catch (IllegalArgumentException exception) {
            throw BusinessException.validation("非法操作类型");
        }
    }

    private String normalizeCode(String value) {
        String normalized = trimToNull(value);
        return normalized == null ? null : normalized.toUpperCase(Locale.ROOT);
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
