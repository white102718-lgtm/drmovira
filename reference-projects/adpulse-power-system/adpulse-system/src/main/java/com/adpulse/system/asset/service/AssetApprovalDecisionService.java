package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 新版多节点审批的决定服务，统一维护权限、状态流转、审计记录和通知。 */
@Service
public class AssetApprovalDecisionService {
    private static final int MAX_BATCH_SIZE = 100;

    private final DynamicAssetFlowMapper flowMapper;
    private final AssetApprovalPrincipalService principalService;
    private final PixelApplicationAssignmentService pixelAssignmentService;
    private final SystemNotificationService notificationService;
    private final ObjectMapper json;

    public AssetApprovalDecisionService(
            DynamicAssetFlowMapper flowMapper,
            AssetApprovalPrincipalService principalService,
            PixelApplicationAssignmentService pixelAssignmentService,
            SystemNotificationService notificationService,
            ObjectMapper json) {
        this.flowMapper = flowMapper;
        this.principalService = principalService;
        this.pixelAssignmentService = pixelAssignmentService;
        this.notificationService = notificationService;
        this.json = json;
    }

    /** 处理一张申请的当前审批节点；审批通过只推进流程，不提前分配库存。 */
    @Transactional
    public void decide(Long applicationId, boolean approved, String remark, CurrentUser actor) {
        decideOne(applicationId, approved, normalizeRemark(remark), actor);
    }

    /** 在同一事务中处理整批审批决定；任一申请失败时回滚全部状态、日志和站内通知。 */
    @Transactional
    public List<Long> batchDecide(AssetRequests.BatchDecision request, CurrentUser actor) {
        validateBatch(request);
        boolean approved = request.action() == AssetRequests.DecisionAction.APPROVE;
        String remark = normalizeRemark(request.remark());
        for (Long applicationId : request.ids()) {
            decideOne(applicationId, approved, remark, actor);
        }
        return List.copyOf(request.ids());
    }

    private void decideOne(Long applicationId, boolean approved, String remark, CurrentUser actor) {
        if (applicationId == null || applicationId <= 0) {
            throw BusinessException.validation("申请 ID 不合法");
        }
        if (flowMapper.lockApplication(applicationId) == null) {
            throw BusinessException.notFound("申请单");
        }
        Map<String, Object> application =
                flowMapper.findApplications(applicationId, null, false).stream()
                        .findFirst()
                        .orElseThrow(() -> BusinessException.notFound("申请单"));
        String status = Objects.toString(application.get("status"), "");
        if ("PROCESSING".equals(status)) {
            if (approved) throw BusinessException.conflict("申请已处理");
            rejectProcessing(applicationId, application, remark, actor);
            return;
        }
        if (!"PENDING".equals(status)) {
            throw BusinessException.conflict("申请已处理");
        }

        List<Map<String, Object>> nodes = list(application.get("nodes"));
        int nodeIndex = intValue(application.get("currentNodeIndex"));
        if (nodeIndex < 0 || nodeIndex >= nodes.size()) {
            throw BusinessException.conflict("当前审批节点不存在");
        }
        Map<String, Object> node = nodes.get(nodeIndex);
        principalService.requireCanApprove(node, actor.userId());
        boolean handlerCaptured = approved && captureLinkedHandler(nodes, node, actor);
        insertApprovalLog(applicationId, approved, actor, remark, nodeIndex, node);

        if (!approved) {
            updateApplication(
                    applicationId,
                    "PENDING",
                    "REJECTED",
                    remark,
                    true,
                    null,
                    null,
                    null,
                    actor.userId());
            notifyUser(
                    number(application.get("requesterId")),
                    "申请已拒绝",
                    application.get("title") + "：" + remark,
                    "/workbench/applications?id=" + applicationId,
                    "APPLICATION",
                    applicationId);
            return;
        }

        if (nodeIndex + 1 < nodes.size()) {
            Map<String, Object> nextNode = nodes.get(nodeIndex + 1);
            AssetApprovalPrincipalService.NodePrincipal nextPrincipal =
                    principalService.normalizeAndResolve(nextNode);
            updateApplication(
                    applicationId,
                    "PENDING",
                    null,
                    null,
                    false,
                    nodeIndex + 1,
                    number(nextNode.get("approverId")),
                    requiredText(nextNode.get("approverName"), "下一审批节点缺少审批人"),
                    actor.userId(),
                    handlerCaptured ? nodes : null);
            notifyUsers(
                    nextPrincipal.eligibleUserIds(),
                    "待审批申请",
                    application.get("title") + " 已到达“" + nextNode.get("name") + "”",
                    "/workbench/approvals?id=" + applicationId,
                    "APPROVAL",
                    applicationId);
            return;
        }

        // 像素自动分配由申请快照中的完成模式驱动，兼容正式 PIXEL 与测试 FLOW_* 标识。
        if (pixelAssignmentService.isPixelAutoAssignment(application)) {
            pixelAssignmentService.assignSelectedPixels(application, actor.userId());
            updateApplication(
                    applicationId,
                    "PENDING",
                    "APPROVED",
                    null,
                    true,
                    null,
                    null,
                    null,
                    actor.userId(),
                    nodes);
            notifyUser(
                    number(application.get("requesterId")),
                    "申请已通过",
                    application.get("title") + " 已审批通过，所选像素已分配到申请项目",
                    "/workbench/applications?id=" + applicationId,
                    "APPLICATION",
                    applicationId);
            return;
        }

        Map<String, Object> handler = workflowHandler(nodes);
        updateApplication(
                applicationId,
                "PENDING",
                "PROCESSING",
                null,
                false,
                null,
                number(handler.get("handlerId")),
                requiredText(handler.get("handlerName"), "审批流程缺少办理人"),
                actor.userId(),
                nodes);
        notifyUser(
                number(handler.get("handlerId")),
                "待处理申请",
                application.get("title") + " 已完成全部审批，请按办理节点配置完成业务操作",
                "/workbench/approvals?id=" + applicationId,
                "PROCESSING",
                applicationId);
    }

    /** 办理人拒绝已完成审批的申请，不触发库存分配或其他办理副作用。 */
    private void rejectProcessing(
            Long applicationId, Map<String, Object> application, String remark, CurrentUser actor) {
        if (remark.isBlank()) throw BusinessException.validation("请填写拒绝原因");
        if (processingHandlerId(application) != actor.userId()) {
            throw BusinessException.conflict("您不是该流程的办理人");
        }
        int handlerNodeIndex = list(application.get("nodes")).size();
        insertApprovalLog(
                applicationId, false, actor, remark, handlerNodeIndex, Map.of("name", "业务办理"));
        updateApplication(
                applicationId,
                "PROCESSING",
                "REJECTED",
                remark,
                true,
                null,
                null,
                null,
                actor.userId());
        notifyUser(
                number(application.get("requesterId")),
                "申请已拒绝",
                application.get("title") + "：" + remark,
                "/workbench/applications?id=" + applicationId,
                "APPLICATION",
                applicationId);
    }

    private void validateBatch(AssetRequests.BatchDecision request) {
        if (request == null
                || request.ids() == null
                || request.ids().isEmpty()
                || request.ids().size() > MAX_BATCH_SIZE) {
            throw BusinessException.validation("批量审批数量必须在 1 到 100 条之间");
        }
        if (request.action() == null) {
            throw BusinessException.validation("审批决定不能为空");
        }
        // 批量通过允许不填写备注；批量拒绝必须向申请人提供可追溯的原因。
        if (request.action() == AssetRequests.DecisionAction.REJECT
                && normalizeRemark(request.remark()).isBlank()) {
            throw BusinessException.validation("请填写拒绝原因");
        }
        if (new LinkedHashSet<>(request.ids()).size() != request.ids().size()) {
            throw BusinessException.validation("审批申请不能重复");
        }
    }

    private String normalizeRemark(String remark) {
        return Objects.toString(remark, "").trim();
    }

    private void insertApprovalLog(
            Long applicationId,
            boolean approved,
            CurrentUser actor,
            String remark,
            int nodeIndex,
            Map<String, Object> node) {
        Map<String, Object> log = new LinkedHashMap<>();
        log.put("applicationId", applicationId);
        log.put("action", approved ? "APPROVED" : "REJECTED");
        log.put("actorId", actor.userId());
        log.put("actorName", actor.displayName());
        log.put("remark", remark);
        log.put("actionData", null);
        log.put("nodeIndex", nodeIndex);
        log.put("nodeName", Objects.toString(node.get("name"), "审批节点"));
        flowMapper.insertApprovalLog(log);
    }

    private void updateApplication(
            Long applicationId,
            String expectedStatus,
            String status,
            String remark,
            boolean decided,
            Integer nodeIndex,
            Long approverId,
            String approverName,
            Long operatorId) {
        updateApplication(
                applicationId,
                expectedStatus,
                status,
                remark,
                decided,
                nodeIndex,
                approverId,
                approverName,
                operatorId,
                null);
    }

    private void updateApplication(
            Long applicationId,
            String expectedStatus,
            String status,
            String remark,
            boolean decided,
            Integer nodeIndex,
            Long approverId,
            String approverName,
            Long operatorId,
            List<Map<String, Object>> nodes) {
        Map<String, Object> update = new LinkedHashMap<>();
        update.put("id", applicationId);
        update.put("expectedStatus", expectedStatus);
        update.put("status", status);
        update.put("remark", remark);
        update.put("decided", decided);
        update.put("nodeIndex", nodeIndex);
        update.put("approverId", approverId);
        update.put("approverName", approverName);
        if (nodes != null) update.put("nodes", stringify(nodes));
        update.put("operatorId", operatorId);
        if (flowMapper.updateApplication(update) != 1) {
            throw BusinessException.conflict("申请状态已变化，请刷新后重试");
        }
    }

    /** 关联节点被通过时固化实际操作人，角色/部门审批不会在配置时预先指定单一人员。 */
    private boolean captureLinkedHandler(
            List<Map<String, Object>> nodes, Map<String, Object> approvedNode, CurrentUser actor) {
        if (nodes.isEmpty()) return false;
        Map<String, Object> handlerNode = nodes.getLast();
        if (!"approval-node".equals(Objects.toString(handlerNode.get("handlerSource"), ""))) {
            return false;
        }
        String approvalNodeId =
                Objects.toString(handlerNode.get("handlerApprovalNodeId"), "").trim();
        if (!approvalNodeId.equals(Objects.toString(approvedNode.get("id"), ""))) return false;
        handlerNode.put("handlerId", actor.userId());
        handlerNode.put("handlerName", actor.displayName());
        return true;
    }

    /** 办理节点关联审批节点时，进入办理阶段使用已固化的实际审批人。 */
    private Map<String, Object> workflowHandler(List<Map<String, Object>> nodes) {
        if (nodes.isEmpty()) return Map.of();
        Map<String, Object> lastNode = nodes.getLast();
        Map<String, Object> handlerNode = lastNode;
        boolean followsApprovalNode =
                "approval-node".equals(Objects.toString(lastNode.get("handlerSource"), ""));
        if (followsApprovalNode) {
            String approvalNodeId =
                    Objects.toString(lastNode.get("handlerApprovalNodeId"), "").trim();
            for (Map<String, Object> node : nodes) {
                if (approvalNodeId.equals(Objects.toString(node.get("id"), ""))) {
                    handlerNode = node;
                    break;
                }
            }
        }
        long handlerId = number(lastNode.get("handlerId"));
        String handlerName = Objects.toString(lastNode.get("handlerName"), "").trim();
        if (followsApprovalNode && handlerId <= 0) {
            handlerId = number(handlerNode.get("approverId"));
            handlerName = Objects.toString(handlerNode.get("approverName"), "").trim();
        }
        if (handlerId <= 0) {
            handlerId = number(lastNode.get("approverId"));
            handlerName = Objects.toString(lastNode.get("approverName"), "").trim();
        }
        return Map.of("handlerId", handlerId, "handlerName", handlerName);
    }

    private String stringify(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("审批节点数据无法保存");
        }
    }

    /** 申请详情查询未必返回办理人快照字段，拒绝办理时从已固化的流程节点回退解析。 */
    private long processingHandlerId(Map<String, Object> application) {
        long handlerId = number(application.get("handlerId"));
        return handlerId > 0
                ? handlerId
                : number(workflowHandler(list(application.get("nodes"))).get("handlerId"));
    }

    private void notifyUser(
            long userId, String title, String content, String path, String type, Long businessId) {
        if (userId <= 0) return;
        notifyUsers(List.of(userId), title, content, path, type, businessId);
    }

    private void notifyUsers(
            List<Long> userIds,
            String title,
            String content,
            String path,
            String type,
            Long businessId) {
        notificationService.notify(
                new NotificationMessage(title, content, path, type, businessId),
                NotificationRecipients.users(userIds));
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value) {
        if (value instanceof List<?>) return (List<Map<String, Object>>) value;
        try {
            return json.readValue(Objects.toString(value, "[]"), List.class);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("审批节点数据损坏");
        }
    }

    private String requiredText(Object value, String message) {
        String text = Objects.toString(value, "").trim();
        if (text.isEmpty()) throw BusinessException.conflict(message);
        return text;
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    private int intValue(Object value) {
        long result = number(value);
        if (result < 0 || result > Integer.MAX_VALUE) return -1;
        return (int) result;
    }
}
