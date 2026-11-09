package com.adpulse.system.asset.service;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;

/** 解析动态审批节点中的指定成员、角色或部门，并统一执行审批资格校验。 */
@Service
public class AssetApprovalPrincipalService {
    private static final String TYPE_DEPARTMENTS = "DEPARTMENTS";
    private static final String TYPE_ROLES = "ROLES";
    private static final String TYPE_USERS = "USERS";
    private final DynamicAssetFlowMapper flowMapper;

    public AssetApprovalPrincipalService(DynamicAssetFlowMapper flowMapper) {
        this.flowMapper = flowMapper;
    }

    /**
     * 规范化节点审批主体并返回当前可审批成员。
     *
     * <p>指定成员按配置快照解析；按角色或部门审批则实时读取成员，确保人员调岗后权限立即生效。
     */
    public NodePrincipal normalizeAndResolve(Map<String, Object> node) {
        String type = Objects.toString(node.get("approverType"), TYPE_USERS).trim().toUpperCase();
        if (TYPE_DEPARTMENTS.equals(type)) return resolveDepartments(node);
        if (TYPE_ROLES.equals(type)) return resolveRoles(node);
        if (!TYPE_USERS.equals(type)) throw BusinessException.validation("审批人类型不合法");
        return resolveUsers(node);
    }

    /** 判断用户是否属于节点当前允许审批的成员范围。 */
    public boolean canApprove(Map<String, Object> node, long userId) {
        try {
            return normalizeAndResolve(node).eligibleUserIds().contains(userId);
        } catch (BusinessException exception) {
            return false;
        }
    }

    /** 校验当前用户的节点审批资格，失败时返回明确的业务提示。 */
    public void requireCanApprove(Map<String, Object> node, long userId) {
        if (!normalizeAndResolve(node).eligibleUserIds().contains(userId)) {
            throw BusinessException.conflict("您不是当前节点的审批成员");
        }
    }

    private NodePrincipal resolveUsers(Map<String, Object> node) {
        List<Long> configuredIds = ids(node.get("approverIds"));
        if (configuredIds.isEmpty()) {
            long legacyId = number(node.get("approverId"));
            if (legacyId > 0) configuredIds = List.of(legacyId);
        }
        if (configuredIds.isEmpty()) throw BusinessException.validation("请至少选择一名审批人");

        List<Map<String, Object>> rows = activeUsers(configuredIds);
        Map<Long, String> namesById = new LinkedHashMap<>();
        rows.forEach(
                row ->
                        namesById.put(
                                number(row.get("id")),
                                Objects.toString(row.get("displayName"), "")));
        if (namesById.size() != configuredIds.size()) {
            throw BusinessException.validation("审批人不存在或已停用，请重新选择");
        }
        List<String> names = configuredIds.stream().map(namesById::get).toList();
        String label = String.join("、", names);
        normalizeNode(
                node,
                TYPE_USERS,
                configuredIds,
                names,
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                label);
        return new NodePrincipal(configuredIds, label);
    }

    private NodePrincipal resolveRoles(Map<String, Object> node) {
        List<Long> roleIds = ids(node.get("roleIds"));
        if (roleIds.isEmpty()) throw BusinessException.validation("请至少选择一个审批角色");

        List<Map<String, Object>> roleRows = activeRoles(roleIds);
        Map<Long, String> roleNamesById = new LinkedHashMap<>();
        roleRows.forEach(
                row ->
                        roleNamesById.put(
                                number(row.get("id")), Objects.toString(row.get("roleName"), "")));
        if (roleNamesById.size() != roleIds.size()) {
            throw BusinessException.validation("审批角色不存在或已停用，请重新选择");
        }
        List<String> roleNames = roleIds.stream().map(roleNamesById::get).toList();
        List<Long> eligibleUserIds = roleMembers(roleIds);
        if (eligibleUserIds.isEmpty()) {
            throw BusinessException.validation("所选审批角色暂无启用成员");
        }
        String label =
                roleNames.stream()
                                .map(name -> "角色：" + name)
                                .reduce((a, b) -> a + "、" + b)
                                .orElse("")
                        + "（"
                        + eligibleUserIds.size()
                        + "人）";
        normalizeNode(
                node,
                TYPE_ROLES,
                eligibleUserIds,
                List.of(),
                roleIds,
                roleNames,
                List.of(),
                List.of(),
                label);
        return new NodePrincipal(eligibleUserIds, label);
    }

    /** 按用户主部门精确解析直属启用成员，不递归纳入下级部门。 */
    private NodePrincipal resolveDepartments(Map<String, Object> node) {
        List<Long> departmentIds = ids(node.get("departmentIds"));
        if (departmentIds.isEmpty()) throw BusinessException.validation("请至少选择一个审批部门");

        List<Map<String, Object>> departmentRows = flowMapper.findActiveDepartments(departmentIds);
        Map<Long, String> departmentNamesById = new LinkedHashMap<>();
        departmentRows.forEach(
                row ->
                        departmentNamesById.put(
                                number(row.get("id")),
                                Objects.toString(row.get("departmentName"), "")));
        if (departmentNamesById.size() != departmentIds.size()) {
            throw BusinessException.validation("审批部门不存在或已停用，请重新选择");
        }
        List<String> departmentNames =
                departmentIds.stream().map(departmentNamesById::get).toList();
        List<Long> eligibleUserIds = flowMapper.findActiveDepartmentMemberIds(departmentIds);
        if (eligibleUserIds.isEmpty()) {
            throw BusinessException.validation("所选审批部门暂无直属启用成员");
        }
        String label =
                departmentNames.stream()
                                .map(name -> "部门：" + name)
                                .reduce((a, b) -> a + "、" + b)
                                .orElse("")
                        + "（"
                        + eligibleUserIds.size()
                        + "人）";
        normalizeNode(
                node,
                TYPE_DEPARTMENTS,
                eligibleUserIds,
                List.of(),
                List.of(),
                List.of(),
                departmentIds,
                departmentNames,
                label);
        return new NodePrincipal(eligibleUserIds, label);
    }

    private void normalizeNode(
            Map<String, Object> node,
            String type,
            List<Long> eligibleUserIds,
            List<String> approverNames,
            List<Long> roleIds,
            List<String> roleNames,
            List<Long> departmentIds,
            List<String> departmentNames,
            String label) {
        node.put("approverType", type);
        node.put("approverIds", TYPE_USERS.equals(type) ? eligibleUserIds : List.of());
        node.put("approverNames", approverNames);
        node.put("roleIds", roleIds);
        node.put("roleNames", roleNames);
        node.put("departmentIds", departmentIds);
        node.put("departmentNames", departmentNames);
        node.put("approverId", eligibleUserIds.get(0));
        node.put("approverName", label);
    }

    private List<Map<String, Object>> activeUsers(List<Long> userIds) {
        return flowMapper.findActiveUsers(userIds);
    }

    private List<Map<String, Object>> activeRoles(List<Long> roleIds) {
        return flowMapper.findActiveRoles(roleIds);
    }

    private List<Long> roleMembers(List<Long> roleIds) {
        return flowMapper.findActiveRoleMemberIds(roleIds);
    }

    private List<Long> ids(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        LinkedHashSet<Long> result = new LinkedHashSet<>();
        for (Object item : values) {
            long id = number(item);
            if (id > 0) result.add(id);
        }
        return new ArrayList<>(result);
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    /** 审批节点规范化后的可审批人员和展示摘要。 */
    public record NodePrincipal(List<Long> eligibleUserIds, String displayName) {}
}
