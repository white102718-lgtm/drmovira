package com.adpulse.system.operationlog.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 系统管理操作审计记录持久化模型。 */
@Data
public class OperationLog {
    private Long id;
    private Long operatorUserId;
    private String operatorDisplayName;
    private String moduleCode;
    private String operationType;
    private String operationName;
    private String targetType;
    private String targetId;
    private String requestMethod;
    private String requestPath;
    private String clientIp;
    private String userAgent;
    private Integer operationResult;
    private Integer failureCode;
    private String failureReason;
    private LocalDateTime operatedAt;
}
