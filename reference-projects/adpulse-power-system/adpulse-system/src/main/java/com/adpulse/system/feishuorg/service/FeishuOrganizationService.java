package com.adpulse.system.feishuorg.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ApplicationConfig;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.ApplicationConfigSave;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncLog;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 飞书应用配置与组织同步历史查询；同步任务由独立编排服务执行。 */
@Service
@PreAuthorize("hasAuthority('system:department:list') and hasAuthority('system:user:list')")
public class FeishuOrganizationService {
    private final FeishuOrganizationMapper mapper;
    private final FeishuSecretCipher secretCipher;

    public FeishuOrganizationService(
            FeishuOrganizationMapper mapper, FeishuSecretCipher secretCipher) {
        this.mapper = mapper;
        this.secretCipher = secretCipher;
    }

    /** 查询飞书应用配置，App Secret不回显。 */
    public ApplicationConfig applicationConfig() {
        FeishuApplicationConfig config = mapper.findApplicationConfig();
        return config == null
                ? new ApplicationConfig(null, "AdPulse 飞书应用", "")
                : new ApplicationConfig(
                        config.getId().toString(), config.getAppName(), config.getAppId());
    }

    /** 新增或更新飞书应用配置，App Secret只以密文保存。 */
    @Transactional
    @PreAuthorize("hasAuthority('system:department:update') and hasAuthority('system:user:update')")
    public ApplicationConfig saveApplicationConfig(ApplicationConfigSave request) {
        FeishuApplicationConfig config = mapper.findApplicationConfig();
        if (config == null && (request.appSecret() == null || request.appSecret().isBlank())) {
            throw BusinessException.validation("首次配置必须填写App Secret");
        }
        if (config == null) config = new FeishuApplicationConfig();
        config.setAppName(request.appName().trim());
        config.setAppId(request.appId().trim());
        config.setUpdatedBy(SecurityContextHelper.currentUserId());
        if (request.appSecret() != null && !request.appSecret().isBlank()) {
            config.setAppSecretCiphertext(secretCipher.encrypt(request.appSecret().trim()));
        }
        if (config.getId() == null) mapper.insertApplicationConfig(config);
        else mapper.updateApplicationConfig(config);
        return new ApplicationConfig(
                config.getId().toString(), config.getAppName(), config.getAppId());
    }

    /** 查询最近一百条组织同步预览和执行记录。 */
    public List<SyncLog> logs() {
        return mapper.findLogs();
    }
}
