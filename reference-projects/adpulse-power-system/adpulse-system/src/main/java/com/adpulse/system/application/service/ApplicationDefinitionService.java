package com.adpulse.system.application.service;

import com.adpulse.system.application.dto.ApplicationDefinitionSaveRequest;
import com.adpulse.system.application.dto.ApplicationDefinitionView;
import com.adpulse.system.application.mapper.ApplicationDefinitionMapper;
import com.adpulse.system.application.model.ApplicationDefinition;
import com.adpulse.system.application.model.ApplicationType;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 申请入口定义管理服务。 */
@Service
public class ApplicationDefinitionService {
    private final ApplicationDefinitionMapper mapper;
    private final ApplicationTypeService applicationTypeService;

    public ApplicationDefinitionService(
            ApplicationDefinitionMapper mapper, ApplicationTypeService applicationTypeService) {
        this.mapper = mapper;
        this.applicationTypeService = applicationTypeService;
    }

    /** 查询申请中心可展示的启用入口。 */
    public List<ApplicationDefinitionView> enabledList() {
        return mapper
                .findAll(null, null, null, true, SecurityContextHelper.currentUserId())
                .stream()
                .map(ApplicationDefinitionView::from)
                .toList();
    }

    /** 查询申请入口管理列表。 */
    public List<ApplicationDefinitionView> managedList(
            String keyword, Integer status, Long approvalConfigId) {
        String normalizedKeyword = keyword == null || keyword.isBlank() ? null : keyword.trim();
        return mapper.findAll(normalizedKeyword, status, approvalConfigId, false, null).stream()
                .map(ApplicationDefinitionView::from)
                .toList();
    }

    /** 新建申请入口。 */
    @Transactional
    public ApplicationDefinitionView create(ApplicationDefinitionSaveRequest request) {
        ApplicationDefinition definition = new ApplicationDefinition();
        apply(definition, request, false);
        Long operatorId = SecurityContextHelper.currentUserId();
        definition.setCreatedBy(operatorId);
        definition.setUpdatedBy(operatorId);
        mapper.insert(definition);
        return view(definition.getId());
    }

    /** 修改申请入口；编码作为稳定业务标识不允许修改。 */
    @Transactional
    public ApplicationDefinitionView update(Long id, ApplicationDefinitionSaveRequest request) {
        ApplicationDefinition definition = requireDefinition(id);
        apply(definition, request, true);
        definition.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.update(definition);
        return view(id);
    }

    /** 软删除申请入口；已有申请单保留其提交时的流程快照，不受入口删除影响。 */
    @Transactional
    public void delete(Long id) {
        requireDefinition(id);
        mapper.softDelete(id, System.currentTimeMillis(), SecurityContextHelper.currentUserId());
    }

    /** 发布审批配置时同步关联申请；同一申请同一时间只关联一个审批配置。 */
    @Transactional
    public void replaceApprovalConfigApplications(Long approvalConfigId, List<Long> definitionIds) {
        List<Long> uniqueIds = definitionIds.stream().distinct().toList();
        if (!uniqueIds.isEmpty() && mapper.countByIds(uniqueIds) != uniqueIds.size()) {
            throw BusinessException.validation("关联申请不存在或已删除");
        }
        Long operatorId = SecurityContextHelper.currentUserId();
        mapper.clearApprovalConfig(approvalConfigId, operatorId);
        if (!uniqueIds.isEmpty()) {
            mapper.assignApprovalConfig(approvalConfigId, uniqueIds, operatorId);
        }
    }

    /** 校验当前用户可以发起该申请，且申请确实关联当前审批配置。 */
    public ApplicationDefinitionView requireEnabledForSubmission(
            Long definitionId, Long approvalConfigId) {
        return enabledList().stream()
                .filter(item -> item.id().equals(definitionId.toString()))
                .filter(item -> item.approvalConfigId().equals(approvalConfigId.toString()))
                .findFirst()
                .orElseThrow(() -> BusinessException.validation("申请不存在、已停用或未关联当前审批配置"));
    }

    private void apply(
            ApplicationDefinition definition,
            ApplicationDefinitionSaveRequest request,
            boolean updating) {
        String requestedCode = trimToNull(request.applicationCode());
        String code =
                requestedCode == null
                        ? (updating ? definition.getApplicationCode() : generateCode())
                        : requestedCode.toUpperCase(Locale.ROOT);
        if (!updating && mapper.countByCode(code) > 0) {
            throw BusinessException.conflict("申请编码已存在");
        }
        if (updating && !definition.getApplicationCode().equals(code)) {
            throw BusinessException.conflict("申请编码创建后不可修改");
        }
        definition.setApplicationCode(code);
        ApplicationType applicationType =
                applicationTypeService.requireEnabled(request.applicationTypeId());
        definition.setApplicationName(request.applicationName().trim());
        definition.setApplicationTypeId(applicationType.getId());
        definition.setDescription(
                request.description() == null ? "" : request.description().trim());
        definition.setIcon(request.icon().trim());
        definition.setVisibility(request.visibility());
        definition.setShowInResourceApplication(request.showInResourceApplication());
        definition.setSortOrder(request.sortOrder());
        definition.setStatus(request.status());
    }

    private ApplicationDefinitionView view(Long id) {
        return ApplicationDefinitionView.from(requireDefinition(id));
    }

    private ApplicationDefinition requireDefinition(Long id) {
        ApplicationDefinition definition = mapper.findById(id);
        if (definition == null) throw BusinessException.notFound("申请入口");
        return definition;
    }

    private String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String generateCode() {
        String code;
        do {
            code =
                    "APP_"
                            + UUID.randomUUID()
                                    .toString()
                                    .replace("-", "")
                                    .substring(0, 12)
                                    .toUpperCase(Locale.ROOT);
        } while (mapper.countByCode(code) > 0);
        return code;
    }
}
