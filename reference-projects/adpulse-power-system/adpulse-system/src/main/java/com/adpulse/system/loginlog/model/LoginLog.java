package com.adpulse.system.loginlog.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 系统登录审计记录持久化模型。 */
@Data
public class LoginLog {
    private Long id;
    private Long userId;
    private String loginIdentifier;
    private String username;
    private String displayName;
    private Integer authStage;
    private Integer loginResult;
    private Integer failureCode;
    private String failureReason;
    private String clientIp;
    private String userAgent;
    private LocalDateTime loginAt;
}
