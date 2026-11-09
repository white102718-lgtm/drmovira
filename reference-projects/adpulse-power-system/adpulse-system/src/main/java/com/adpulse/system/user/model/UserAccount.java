package com.adpulse.system.user.model;

import com.adpulse.system.common.model.AuditedEntity;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.LocalDateTime;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 系统用户持久化模型。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class UserAccount extends AuditedEntity {
    /** 仅由人工数据库脚本授予，普通用户维护接口不能修改。 */
    private boolean superAdmin;

    private String username;
    private String phone;
    @JsonIgnore private String passwordHash;
    private String displayName;
    private String englishNickname;
    private String realName;
    private Long primaryDepartmentId;
    private String email;
    private String avatarUrl;
    private Integer status;
    private Integer ipAccessMode;
    private Integer mfaStatus;
    @JsonIgnore private String mfaSecretCiphertext;
    private LocalDateTime mfaBoundAt;
    @JsonIgnore private Long mfaLastUsedCounter;
    private LocalDateTime passwordChangedAt;
    private Integer loginFailedCount;
    private LocalDateTime lockedUntil;
    private LocalDateTime lastLoginAt;
    private String lastLoginIp;
    private String remark;
    private String sourceType;
    private String tenantKey;
    private String externalId;
    private String feishuOpenId;
    private String feishuUnionId;
    private java.time.LocalDateTime lastSyncedAt;
}
