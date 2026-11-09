package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.AssetApplication;
import com.adpulse.system.asset.model.AssetApplicationComment;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 管理资产审批流程评论及参与人权限。 */
@Service
public class AssetApprovalCommentService {
    private final AssetMapper mapper;
    private final ObjectMapper json;
    private final AssetApprovalPrincipalService principalService;

    public AssetApprovalCommentService(
            AssetMapper mapper, ObjectMapper json, AssetApprovalPrincipalService principalService) {
        this.mapper = mapper;
        this.json = json;
        this.principalService = principalService;
    }

    /** 查询当前用户有权查看的流程评论。 */
    public List<AssetViews.ApprovalCommentView> comments(Long applicationId) {
        AssetApplication application = requireApplication(applicationId);
        requireParticipantRole(application, SecurityContextHelper.currentUserId());
        return mapper.findApplicationComments(applicationId).stream().map(this::toView).toList();
    }

    /** 校验当前用户是否为申请流程参与人，供申请详情等只读接口复用。 */
    public void requireParticipant(Long applicationId) {
        AssetApplication application = requireApplication(applicationId);
        requireParticipantRole(application, SecurityContextHelper.currentUserId());
    }

    /**
     * 批量返回当前用户有权查看的申请摘要，供资产列表避免逐条拉取申请详情。
     *
     * <p>复用详情接口的参与人校验，未授权的申请不会出现在结果中。
     */
    public List<AssetViews.ApplicationSummary> applicationSummaries(List<Long> applicationIds) {
        if (applicationIds.isEmpty()) return List.of();
        long userId = SecurityContextHelper.currentUserId();
        return mapper.findApplicationsByIds(applicationIds).stream()
                .filter(application -> participantRole(application, userId) != null)
                .map(
                        application ->
                                new AssetViews.ApplicationSummary(
                                        application.getId().toString(),
                                        application.getStatus(),
                                        application.getRequesterName()))
                .toList();
    }

    /** 以服务端确认的参与人身份发布流程评论。 */
    @Transactional
    public AssetViews.ApprovalCommentView comment(
            Long applicationId, AssetRequests.ApprovalCommentCreate request) {
        AssetApplication application = requireApplication(applicationId);
        CurrentUser actor = SecurityContextHelper.currentUser();
        AssetApplicationComment comment = new AssetApplicationComment();
        comment.setApplicationId(applicationId);
        comment.setActorId(actor.userId());
        comment.setActorName(actor.displayName());
        comment.setActorRole(requireParticipantRole(application, actor.userId()));
        comment.setContent(request.content().trim());
        mapper.insertApplicationComment(comment);
        return toView(mapper.findApplicationComment(comment.getId()));
    }

    private AssetViews.ApprovalCommentView toView(AssetApplicationComment comment) {
        return new AssetViews.ApprovalCommentView(
                comment.getId().toString(),
                comment.getActorName(),
                comment.getActorRole(),
                comment.getCreatedAt(),
                comment.getContent());
    }

    private AssetApplication requireApplication(Long applicationId) {
        AssetApplication application = mapper.findApplication(applicationId);
        if (application == null) throw BusinessException.notFound("申请单");
        return application;
    }

    /** 返回当前用户在流程中的稳定角色，拒绝无关人员通过前端伪造身份发表评论。 */
    private String requireParticipantRole(AssetApplication application, Long userId) {
        String role = participantRole(application, userId);
        if (role == null) throw BusinessException.conflict("当前用户不是该审批流程参与人");
        return role;
    }

    /** 返回当前用户在申请中的角色；无权限时返回 null，便于批量查询过滤。 */
    private String participantRole(AssetApplication application, Long userId) {
        List<Map<String, Object>> nodes = parseNodes(application.getNodesSnapshot());
        boolean isHandler =
                nodes.stream().anyMatch(node -> matchesUser(node.get("handlerId"), userId));
        boolean isApprover =
                Objects.equals(application.getApproverId(), userId)
                        || nodes.stream()
                                .anyMatch(node -> principalService.canApprove(node, userId));
        // 同一测试账号可能兼任多个角色，评论身份优先反映当前流程阶段的实际职责。
        if ("PROCESSING".equals(application.getStatus()) && isHandler) {
            return "办理人";
        }
        if (isApprover) return "审批人";
        if (Objects.equals(application.getRequesterId(), userId)) return "申请人";
        if (isHandler) return "办理人";
        Map<String, Object> formData = parseMap(application.getFormData());
        if (containsUserId(formData.get("_ccUserIds"), userId)) return "抄送人";
        return null;
    }

    private boolean containsUserId(Object value, Long userId) {
        if (value instanceof List<?> values) {
            return values.stream().anyMatch(item -> matchesUser(item, userId));
        }
        return Arrays.stream(Objects.toString(value, "").split(","))
                .anyMatch(item -> matchesUser(item.trim(), userId));
    }

    private boolean matchesUser(Object value, Long userId) {
        return Objects.toString(value, "").equals(userId.toString());
    }

    private List<Map<String, Object>> parseNodes(String value) {
        if (value == null || value.isBlank()) return List.of();
        try {
            return json.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("审批流程快照损坏，请联系管理员");
        }
    }

    private Map<String, Object> parseMap(String value) {
        if (value == null || value.isBlank()) return Map.of();
        try {
            return json.readValue(value, new TypeReference<>() {});
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("申请数据快照损坏，请联系管理员");
        }
    }
}
