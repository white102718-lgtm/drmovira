package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 审批与办理转交服务，统一维护主部门范围、办理权限和审计轨迹。 */
@Service
public class AssetApprovalTransferService {
    private final DynamicAssetFlowMapper flowMapper;
    private final AssetApprovalPrincipalService principalService;
    private final SystemNotificationService notificationService;
    private final ObjectMapper json;

    public AssetApprovalTransferService(
            DynamicAssetFlowMapper flowMapper,
            AssetApprovalPrincipalService principalService,
            SystemNotificationService notificationService,
            ObjectMapper json) {
        this.flowMapper = flowMapper;
        this.principalService = principalService;
        this.notificationService = notificationService;
        this.json = json;
    }

    /** 返回当前审批人或办理人主部门内的其他启用用户。 */
    public List<AssetViews.ApprovalTransferCandidate> candidates(
            Long applicationId, CurrentUser actor) {
        TransferContext context = requireTransferContext(applicationId, actor, false);
        return flowMapper
                .findActiveUsersByPrimaryDepartment(context.departmentId(), actor.userId())
                .stream()
                .map(this::candidate)
                .toList();
    }

    /** 转交当前审批或办理节点；申请状态不变，仅替换当前负责人并写入审计日志。 */
    @Transactional
    public void transfer(
            Long applicationId, AssetRequests.ApprovalTransfer request, CurrentUser actor) {
        TransferContext context = requireTransferContext(applicationId, actor, true);
        Map<String, Object> recipient =
                flowMapper
                        .findActiveUsersByPrimaryDepartment(context.departmentId(), actor.userId())
                        .stream()
                        .filter(row -> number(row.get("id")) == request.recipientId())
                        .findFirst()
                        .orElseThrow(() -> BusinessException.validation("接收人必须是当前办理人主部门内的其他启用用户"));

        long recipientId = number(recipient.get("id"));
        String recipientName = requiredText(recipient.get("name"), "接收人名称不存在");
        Map<String, Object> node;
        if (context.processing()) {
            // 办理人是进入办理阶段时的快照；转交只改快照，不回写已完成的审批节点。
            node = context.nodes().getLast();
            node.put("handlerId", recipientId);
            node.put("handlerName", recipientName);
        } else {
            node = context.nodes().get(context.nodeIndex());
            node.put("approverType", "USERS");
            node.put("approverIds", List.of(recipientId));
            node.put("approverNames", List.of(recipientName));
            node.put("roleIds", List.of());
            node.put("roleNames", List.of());
            node.put("approverId", recipientId);
            node.put("approverName", recipientName);
        }

        Map<String, Object> update = new LinkedHashMap<>();
        update.put("id", applicationId);
        update.put("expectedStatus", context.status());
        update.put("status", null);
        update.put("remark", null);
        update.put("decided", false);
        update.put("nodeIndex", null);
        update.put("approverId", recipientId);
        update.put("approverName", recipientName);
        update.put("nodes", stringify(context.nodes()));
        update.put("operatorId", actor.userId());
        if (flowMapper.updateApplication(update) != 1) {
            throw BusinessException.conflict("申请状态已变化，请刷新后重试");
        }

        Map<String, Object> actionData = new LinkedHashMap<>();
        actionData.put("actorDepartmentId", Long.toString(context.departmentId()));
        actionData.put("actorDepartmentName", context.departmentName());
        actionData.put("recipientId", Long.toString(recipientId));
        actionData.put("recipientName", recipientName);
        actionData.put("recipientDepartmentId", Long.toString(context.departmentId()));
        actionData.put("recipientDepartmentName", context.departmentName());

        Map<String, Object> log = new LinkedHashMap<>();
        log.put("applicationId", applicationId);
        log.put("action", "TRANSFERRED");
        log.put("actorId", actor.userId());
        log.put("actorName", actor.displayName());
        log.put("remark", request.remark().trim());
        log.put("actionData", stringify(actionData));
        log.put("nodeIndex", context.auditNodeIndex());
        log.put(
                "nodeName",
                context.processing() ? "业务办理" : Objects.toString(node.get("name"), "审批节点"));
        flowMapper.insertApprovalLog(log);

        notificationService.notify(
                new NotificationMessage(
                        context.processing() ? "待处理申请" : "待审批申请",
                        actor.displayName() + "已将“" + context.title() + "”转交给您",
                        "/workbench/approvals?id=" + applicationId,
                        context.processing() ? "PROCESSING" : "APPROVAL",
                        applicationId),
                NotificationRecipients.users(List.of(recipientId)));
    }

    private TransferContext requireTransferContext(
            Long applicationId, CurrentUser actor, boolean lock) {
        if (applicationId == null || applicationId <= 0) {
            throw BusinessException.validation("申请 ID 不合法");
        }
        if (lock && flowMapper.lockApplication(applicationId) == null) {
            throw BusinessException.notFound("申请单");
        }
        Map<String, Object> application =
                flowMapper.findApplications(applicationId, null, false).stream()
                        .findFirst()
                        .orElseThrow(() -> BusinessException.notFound("申请单"));
        String status = Objects.toString(application.get("status"), "");
        if (!List.of("PENDING", "PROCESSING").contains(status)) {
            throw BusinessException.conflict("申请已处理，不能转交");
        }
        List<Map<String, Object>> nodes = list(application.get("nodes"));
        if (nodes.isEmpty()) {
            throw BusinessException.conflict("当前流程节点不存在");
        }
        int nodeIndex = intValue(application.get("currentNodeIndex"));
        boolean processing = "PROCESSING".equals(status);
        if (processing) {
            if (number(application.get("approverId")) != actor.userId()) {
                throw BusinessException.conflict("您不是该流程的办理人");
            }
        } else {
            if (nodeIndex < 0 || nodeIndex >= nodes.size()) {
                throw BusinessException.conflict("当前审批节点不存在");
            }
            principalService.requireCanApprove(nodes.get(nodeIndex), actor.userId());
        }
        Map<String, Object> department = flowMapper.findActivePrimaryDepartment(actor.userId());
        if (department == null) {
            throw BusinessException.validation("当前办理人未设置有效主部门，无法转交");
        }
        long departmentId = number(department.get("departmentId"));
        if (departmentId <= 0) {
            throw BusinessException.validation("当前办理人未设置有效主部门，无法转交");
        }
        return new TransferContext(
                nodes,
                nodeIndex,
                processing ? nodes.size() : nodeIndex,
                status,
                processing,
                departmentId,
                requiredText(department.get("departmentName"), "当前办理人的主部门名称不存在"),
                Objects.toString(application.get("title"), "申请单"));
    }

    private AssetViews.ApprovalTransferCandidate candidate(Map<String, Object> row) {
        return new AssetViews.ApprovalTransferCandidate(
                Long.toString(number(row.get("id"))),
                requiredText(row.get("name"), "候选人名称不存在"),
                Long.toString(number(row.get("departmentId"))),
                requiredText(row.get("departmentName"), "候选人主部门名称不存在"));
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

    private String stringify(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("审批转交数据序列化失败");
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

    private record TransferContext(
            List<Map<String, Object>> nodes,
            int nodeIndex,
            int auditNodeIndex,
            String status,
            boolean processing,
            long departmentId,
            String departmentName,
            String title) {}
}
