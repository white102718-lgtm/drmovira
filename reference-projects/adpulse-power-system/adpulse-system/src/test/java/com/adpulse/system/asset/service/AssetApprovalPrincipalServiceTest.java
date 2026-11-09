package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 资产审批节点指定成员、角色或直属部门授权测试。 */
@ExtendWith(MockitoExtension.class)
class AssetApprovalPrincipalServiceTest {
    @Mock private DynamicAssetFlowMapper flowMapper;
    private AssetApprovalPrincipalService service;

    @BeforeEach
    void setUp() {
        service = new AssetApprovalPrincipalService(flowMapper);
    }

    @Test
    void shouldAllowAnyConfiguredUserToApprove() {
        when(flowMapper.findActiveUsers(List.of(11L, 12L)))
                .thenReturn(
                        List.of(
                                Map.of("id", 11L, "displayName", "甲"),
                                Map.of("id", 12L, "displayName", "乙")));
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("approverType", "USERS");
        node.put("approverIds", List.of("11", "12"));

        AssetApprovalPrincipalService.NodePrincipal principal = service.normalizeAndResolve(node);

        assertThat(principal.eligibleUserIds()).containsExactly(11L, 12L);
        assertThat(service.canApprove(node, 12L)).isTrue();
        assertThat(node.get("approverName")).isEqualTo("甲、乙");
    }

    @Test
    void shouldResolveCurrentActiveMembersForRoles() {
        when(flowMapper.findActiveRoles(List.of(21L)))
                .thenReturn(List.of(Map.of("id", 21L, "roleName", "媒介负责人")));
        when(flowMapper.findActiveRoleMemberIds(List.of(21L))).thenReturn(List.of(101L, 102L));
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("approverType", "ROLES");
        node.put("roleIds", List.of("21"));

        AssetApprovalPrincipalService.NodePrincipal principal = service.normalizeAndResolve(node);

        assertThat(principal.eligibleUserIds()).containsExactly(101L, 102L);
        assertThat(service.canApprove(node, 102L)).isTrue();
        assertThat(node.get("approverName")).isEqualTo("角色：媒介负责人（2人）");
    }

    @Test
    void shouldResolveOnlyDirectActiveMembersForDepartments() {
        when(flowMapper.findActiveDepartments(List.of(31L, 32L)))
                .thenReturn(
                        List.of(
                                Map.of("id", 31L, "departmentName", "媒介一部"),
                                Map.of("id", 32L, "departmentName", "媒介二部")));
        when(flowMapper.findActiveDepartmentMemberIds(List.of(31L, 32L)))
                .thenReturn(List.of(201L, 202L));
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("approverType", "DEPARTMENTS");
        node.put("departmentIds", List.of("31", "32"));

        AssetApprovalPrincipalService.NodePrincipal principal = service.normalizeAndResolve(node);

        assertThat(principal.eligibleUserIds()).containsExactly(201L, 202L);
        assertThat(service.canApprove(node, 202L)).isTrue();
        assertThat(node.get("approverName")).isEqualTo("部门：媒介一部、部门：媒介二部（2人）");
        assertThat(node.get("departmentNames")).isEqualTo(List.of("媒介一部", "媒介二部"));
    }

    @Test
    void shouldRejectDepartmentWithoutDirectActiveMembers() {
        when(flowMapper.findActiveDepartments(List.of(31L)))
                .thenReturn(List.of(Map.of("id", 31L, "departmentName", "媒介一部")));
        when(flowMapper.findActiveDepartmentMemberIds(List.of(31L))).thenReturn(List.of());
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("approverType", "DEPARTMENTS");
        node.put("departmentIds", List.of("31"));

        assertThatThrownBy(() -> service.normalizeAndResolve(node))
                .isInstanceOf(BusinessException.class)
                .hasMessage("所选审批部门暂无直属启用成员");
    }

    @Test
    void shouldRejectUserOutsideCurrentNodeScope() {
        when(flowMapper.findActiveUsers(List.of(11L)))
                .thenReturn(List.of(Map.of("id", 11L, "displayName", "甲")));
        Map<String, Object> node = new LinkedHashMap<>();
        node.put("approverType", "USERS");
        node.put("approverIds", List.of("11"));

        assertThatThrownBy(() -> service.requireCanApprove(node, 99L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("您不是当前节点的审批成员");
    }
}
