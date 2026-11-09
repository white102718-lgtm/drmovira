package com.adpulse.system.feishuorg.model;

import lombok.Data;

/** 复用飞书应用配置表的组织同步凭证模型。 */
@Data
public class FeishuApplicationConfig {
    private Long id;
    private String appName;
    private String appId;
    private String appSecretCiphertext;
    private Long updatedBy;
}
