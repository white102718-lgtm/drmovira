package com.adpulse.main.project.sync;

import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.AgencyLine;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.model.ProjectUserReference;
import com.adpulse.main.project.service.ProjectService.ProjectException;
import java.net.URI;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 在独立事务中新增或覆盖一行 Google Sheet 代理线数据。 */
@Service
public class AgencyLineSheetRowService {
    private static final Set<String> TERMINAL_PROJECT_STATUSES = Set.of("ended", "archived");
    private static final String DEFAULT_PLATFORM = "facebook";

    private final ProjectMapper projectMapper;
    private final AgencyLineSyncMapper syncMapper;
    private final IntegrationSecretCipher cipher;

    public AgencyLineSheetRowService(
            ProjectMapper projectMapper,
            AgencyLineSyncMapper syncMapper,
            IntegrationSecretCipher cipher) {
        this.projectMapper = projectMapper;
        this.syncMapper = syncMapper;
        this.cipher = cipher;
    }

    /** 区分“列不存在”和“列存在但值为空”，以落实保留或清空的覆盖语义。 */
    public record FieldValue(boolean present, String value) {
        public static FieldValue absent() {
            return new FieldValue(false, null);
        }
    }

    /** 单行同步输入；代理线名称必填，投放平台缺失或为空时默认 Facebook。 */
    public record SheetRow(
            String name,
            String platform,
            FieldValue type,
            FieldValue pixelName,
            FieldValue pixelId,
            FieldValue token,
            FieldValue testCode,
            FieldValue deliveryUrl,
            FieldValue optimizerName,
            FieldValue cloakUrl) {}

    /** 每行独立提交；项目媒体平台不限制代理线平台，失败只回滚当前行。 */
    @Transactional
    public void synchronize(
            Long projectId,
            Long batchId,
            int sheetRowNumber,
            SheetRow input,
            Long operatorId,
            String operatorName) {
        Project project = projectMapper.findProject(projectId);
        if (project == null) throw new ProjectException("项目不存在或已被删除");
        if (TERMINAL_PROJECT_STATUSES.contains(project.getStatus())) {
            throw new ProjectException("结束或归档项目不允许同步代理线");
        }

        String lineName = required(input.name(), "代理线名称", 80);
        String platform = normalizePlatform(input.platform());
        if (projectMapper.countEnabledDictionaryValue("AD_MEDIA", platform) != 1) {
            throw new ProjectException("投放平台未启用：" + platform);
        }

        AgencyLine existing = projectMapper.findAgencyLineByNameForUpdate(lineName);
        if (existing != null
                && existing.getProjectId() != null
                && !projectId.equals(existing.getProjectId())) {
            throw new ProjectException("同名代理线已属于其他项目");
        }
        boolean creating = existing == null;
        AgencyLine line = creating ? new AgencyLine() : existing;
        String previousDeliveryUrl = trimToNull(line.getDeliveryUrl());

        line.setProjectId(projectId);
        line.setLineName(lineName);
        line.setPlatformValue(platform);
        applyText(input.type(), 50, "类型", line::setType);
        applyUrl(input.deliveryUrl(), 2000, "投放链接", line::setDeliveryUrl);
        applyText(input.pixelName(), 255, "像素名称", line::setPixelName);
        applyText(input.pixelId(), 100, "像素ID", line::setPixelId);
        applyToken(input.token(), line);
        applyText(input.testCode(), 200, "测试代码", line::setTestCode);
        applyUrl(input.cloakUrl(), 2000, "斗篷链接", line::setCloakUrl);
        applyOptimizer(input.optimizerName(), line);
        line.setUpdatedBy(operatorId);

        try {
            if (creating) {
                line.setRequestId("agency-line-sheet-sync-" + batchId + "-" + sheetRowNumber);
                line.setCreatedBy(operatorId);
                projectMapper.insertAgencyLine(line);
            } else {
                projectMapper.updateAgencyLine(line);
            }
        } catch (DuplicateKeyException exception) {
            throw new ProjectException("代理线数据已发生变化，请下次同步重试");
        }
        if (creating || !Objects.equals(previousDeliveryUrl, line.getDeliveryUrl())) {
            recordDeliveryUrlVersion(line, operatorId, operatorName);
        }
    }

    private void applyOptimizer(FieldValue field, AgencyLine line) {
        if (!field.present()) return;
        String name = trimToNull(field.value());
        if (name == null) {
            line.setOptimizerId(null);
            line.setOptimizerName(null);
            line.setOptimizerStatus(null);
            return;
        }
        if (name.length() > 100) throw new ProjectException("投手名称不能超过100个字符");
        List<ProjectUserReference> users = syncMapper.findActiveUsersByName(name);
        if (users.isEmpty()) throw new ProjectException("未找到启用的投手：" + name);
        if (users.size() > 1) throw new ProjectException("投手姓名存在重名，请先处理用户数据：" + name);
        ProjectUserReference user = users.getFirst();
        line.setOptimizerId(user.id());
        line.setOptimizerName(user.displayName());
        line.setOptimizerStatus(user.status());
    }

    private void applyToken(FieldValue field, AgencyLine line) {
        if (!field.present()) return;
        String token = trimToNull(field.value());
        if (token != null && token.length() > 10000) {
            throw new ProjectException("Token不能超过10000个字符");
        }
        line.setTokenCiphertext(token == null ? null : cipher.encrypt(token));
    }

    private void applyText(
            FieldValue field,
            int maxLength,
            String label,
            java.util.function.Consumer<String> setter) {
        if (!field.present()) return;
        String value = trimToNull(field.value());
        if (value != null && value.length() > maxLength) {
            throw new ProjectException(label + "不能超过" + maxLength + "个字符");
        }
        setter.accept(value);
    }

    private void applyUrl(
            FieldValue field,
            int maxLength,
            String label,
            java.util.function.Consumer<String> setter) {
        if (!field.present()) return;
        String value = trimToNull(field.value());
        if (value != null && value.length() > maxLength) {
            throw new ProjectException(label + "不能超过" + maxLength + "个字符");
        }
        if (value != null) {
            try {
                String scheme = URI.create(value).getScheme();
                if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) {
                    throw new IllegalArgumentException();
                }
            } catch (RuntimeException exception) {
                throw new ProjectException(label + "必须是有效的http(s)地址");
            }
        }
        setter.accept(value);
    }

    private String normalizePlatform(String raw) {
        String value = trimToNull(raw);
        if (value == null) return DEFAULT_PLATFORM;
        if (value.length() > 100) throw new ProjectException("投放平台不能超过100个字符");
        return value.toLowerCase(Locale.ROOT);
    }

    private String required(String raw, String label, int maxLength) {
        String value = trimToNull(raw);
        if (value == null) throw new ProjectException(label + "不能为空");
        if (value.length() > maxLength) {
            throw new ProjectException(label + "不能超过" + maxLength + "个字符");
        }
        return value;
    }

    private String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private void recordDeliveryUrlVersion(
            AgencyLine line, Long operatorId, String operatorName) {
        int versionNo = Math.max(1, projectMapper.nextAgencyLineDeliveryUrlVersion(line.getId()));
        if (line.getDeliveryUrl() == null && versionNo == 1) return;
        projectMapper.insertAgencyLineDeliveryUrlHistory(
                line.getId(),
                versionNo,
                line.getDeliveryUrl(),
                operatorId,
                operatorName == null || operatorName.isBlank() ? "系统定时同步" : operatorName);
    }
}
