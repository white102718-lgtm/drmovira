package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 审批转交的主部门范围、权限切换和审计写入测试。 */
@ExtendWith(MockitoExtension.class)
class AssetApprovalTransferServiceTest {
    @Mock private DynamicAssetFlowMapper flowMapper;
    @Mock private AssetApprovalPrincipalService principalService;
    @Mock private SystemNotificationService notificationService;
    private AssetApprovalTransferService service;
    private CurrentUser actor;

    @BeforeEach
    void setUp() {
        service =
                new AssetApprovalTransferService(
                        flowMapper, principalService, notificationService, new ObjectMapper());
        actor = new CurrentUser(10L, "session", "张三", List.of());
    }

    @Test
    void shouldListOnlyActiveColleaguesFromHandlersPrimaryDepartment() {
        stubTransferContext();
        when(flowMapper.findActiveUsersByPrimaryDepartment(20L, 10L))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id",
                                        11L,
                                        "name",
                                        "李四",
                                        "departmentId",
                                        20L,
                                        "departmentName",
                                        "媒介部")));

        var candidates = service.candidates(60L, actor);

        assertThat(candidates).hasSize(1);
        assertThat(candidates.getFirst().id()).isEqualTo("11");
        assertThat(candidates.getFirst().departmentId()).isEqualTo("20");
        verify(principalService).requireCanApprove(any(), org.mockito.ArgumentMatchers.eq(10L));
    }

    @Test
    void shouldTransferPendingNodeAndWriteRecipientAuditData() throws Exception {
        when(flowMapper.lockApplication(60L)).thenReturn(60L);
        stubTransferContext();
        when(flowMapper.findActiveUsersByPrimaryDepartment(20L, 10L))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id",
                                        11L,
                                        "name",
                                        "李四",
                                        "departmentId",
                                        20L,
                                        "departmentName",
                                        "媒介部")));
        when(flowMapper.updateApplication(any())).thenReturn(1);

        service.transfer(60L, new AssetRequests.ApprovalTransfer(11L, "请协助办理"), actor);

        ArgumentCaptor<Map<String, Object>> updateCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper).updateApplication(updateCaptor.capture());
        assertThat(updateCaptor.getValue())
                .containsEntry("approverId", 11L)
                .containsEntry("approverName", "李四");
        List<?> updatedNodes =
                new ObjectMapper()
                        .readValue(updateCaptor.getValue().get("nodes").toString(), List.class);
        Map<?, ?> updatedNode = (Map<?, ?>) updatedNodes.getFirst();
        assertThat(updatedNode.get("approverIds")).isEqualTo(List.of(11));

        ArgumentCaptor<Map<String, Object>> logCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper).insertApprovalLog(logCaptor.capture());
        assertThat(logCaptor.getValue())
                .containsEntry("action", "TRANSFERRED")
                .containsEntry("actorId", 10L)
                .containsEntry("remark", "请协助办理");
        assertThat(logCaptor.getValue().get("actionData").toString())
                .contains("\"recipientId\":\"11\"")
                .contains("\"recipientDepartmentId\":\"20\"");
    }

    @Test
    void shouldTransferProcessingHandlerWithoutChangingApprovedNode() throws Exception {
        when(flowMapper.lockApplication(60L)).thenReturn(60L);
        when(flowMapper.findApplications(60L, null, false))
                .thenReturn(List.of(processingApplication()));
        when(flowMapper.findActivePrimaryDepartment(10L))
                .thenReturn(Map.of("departmentId", 20L, "departmentName", "媒介部"));
        when(flowMapper.findActiveUsersByPrimaryDepartment(20L, 10L))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id",
                                        11L,
                                        "name",
                                        "李四",
                                        "departmentId",
                                        20L,
                                        "departmentName",
                                        "媒介部")));
        when(flowMapper.updateApplication(any())).thenReturn(1);

        service.transfer(60L, new AssetRequests.ApprovalTransfer(11L, "请协助办理"), actor);

        ArgumentCaptor<Map<String, Object>> updateCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper).updateApplication(updateCaptor.capture());
        assertThat(updateCaptor.getValue())
                .containsEntry("expectedStatus", "PROCESSING")
                .containsEntry("approverId", 11L)
                .containsEntry("approverName", "李四");
        List<?> updatedNodes =
                new ObjectMapper()
                        .readValue(updateCaptor.getValue().get("nodes").toString(), List.class);
        @SuppressWarnings("unchecked")
        Map<String, Object> approvedNode = (Map<String, Object>) updatedNodes.getFirst();
        assertThat(approvedNode)
                .containsEntry("approverId", 10)
                .containsEntry("approverName", "张三")
                .containsEntry("handlerId", 11)
                .containsEntry("handlerName", "李四");

        ArgumentCaptor<Map<String, Object>> logCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper).insertApprovalLog(logCaptor.capture());
        assertThat(logCaptor.getValue())
                .containsEntry("action", "TRANSFERRED")
                .containsEntry("nodeIndex", 1)
                .containsEntry("nodeName", "业务办理");
    }

    @Test
    void shouldRejectProcessingTransferFromFormerHandler() {
        Map<String, Object> application = processingApplication();
        application.put("approverId", 12L);
        when(flowMapper.findApplications(60L, null, false)).thenReturn(List.of(application));

        assertThatThrownBy(() -> service.candidates(60L, actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("您不是该流程的办理人");
    }

    @Test
    void shouldRejectRecipientOutsideHandlersPrimaryDepartment() {
        when(flowMapper.lockApplication(60L)).thenReturn(60L);
        stubTransferContext();
        when(flowMapper.findActiveUsersByPrimaryDepartment(20L, 10L)).thenReturn(List.of());

        assertThatThrownBy(
                        () ->
                                service.transfer(
                                        60L,
                                        new AssetRequests.ApprovalTransfer(99L, "请协助办理"),
                                        actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("接收人必须是当前办理人主部门内的其他启用用户");
    }

    @Test
    void shouldRejectTransferWhenHandlerHasNoActivePrimaryDepartment() {
        when(flowMapper.findApplications(60L, null, false)).thenReturn(List.of(application()));
        when(flowMapper.findActivePrimaryDepartment(10L)).thenReturn(null);

        assertThatThrownBy(() -> service.candidates(60L, actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("当前办理人未设置有效主部门，无法转交");
    }

    private void stubTransferContext() {
        when(flowMapper.findApplications(60L, null, false)).thenReturn(List.of(application()));
        when(flowMapper.findActivePrimaryDepartment(10L))
                .thenReturn(Map.of("departmentId", 20L, "departmentName", "媒介部"));
    }

    private Map<String, Object> application() {
        Map<String, Object> application = new LinkedHashMap<>();
        application.put("id", 60L);
        application.put("status", "PENDING");
        application.put("title", "开户审批");
        application.put("currentNodeIndex", 0);
        application.put(
                "nodes",
                "[{\"name\":\"媒介审批\",\"approverType\":\"USERS\","
                        + "\"approverIds\":[10],\"approverId\":10,\"approverName\":\"张三\"}]");
        return application;
    }

    private Map<String, Object> processingApplication() {
        Map<String, Object> application = application();
        application.put("status", "PROCESSING");
        application.put("approverId", 10L);
        application.put(
                "nodes",
                "[{\"name\":\"媒介审批\",\"approverType\":\"USERS\","
                        + "\"approverIds\":[10],\"approverId\":10,\"approverName\":\"张三\","
                        + "\"handlerId\":10,\"handlerName\":\"张三\"}]");
        return application;
    }
}
