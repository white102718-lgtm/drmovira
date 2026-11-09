package com.adpulse.system.operationlog.audit;

/** 操作审计切面传递给持久化服务的安全请求上下文。 */
public record OperationLogContext(
        Long operatorUserId,
        String operatorDisplayName,
        String moduleCode,
        OperationType operationType,
        String operationName,
        String targetType,
        String targetId,
        String requestMethod,
        String requestPath,
        String clientIp,
        String userAgent) {}
