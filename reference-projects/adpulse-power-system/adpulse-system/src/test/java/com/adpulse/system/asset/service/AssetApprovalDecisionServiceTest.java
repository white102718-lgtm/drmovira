package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
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
import org.springframework.transaction.annotation.Transactional;

/** 新版审批决定的批量事务、节点流转和输入边界测试。 */
@ExtendWith(MockitoExtension.class)
class AssetApprovalDecisionServiceTest {
    @Mock private DynamicAssetFlowMapper flowMapper;
    @Mock private AssetApprovalPrincipalService principalService;
    @Mock private PixelApplicationAssignmentService pixelAssignmentService;
    @Mock private SystemNotificationService notificationService;
    private AssetApprovalDecisionService service;
    private CurrentUser actor;

    @BeforeEach
    void setUp() {
        service =
                new AssetApprovalDecisionService(
                        flowMapper,
                        principalService,
                        pixelAssignmentService,
                        notificationService,
                        new ObjectMapper());
        actor = new CurrentUser(10L, "session", "审批人", List.of());
    }

    @Test
    void shouldBatchApproveWithoutCheckingOrAllocatingInventory() throws Exception {
        when(flowMapper.lockApplication(anyLong()))
                .thenAnswer(invocation -> invocation.getArgument(0));
        when(flowMapper.findApplications(anyLong(), isNull(), eq(false)))
                .thenAnswer(invocation -> List.of(application(invocation.getArgument(0))));
        when(flowMapper.updateApplication(any())).thenReturn(1);

        service.batchDecide(
                new AssetRequests.BatchDecision(
                        List.of(63L, 66L), AssetRequests.DecisionAction.APPROVE, ""),
                actor);

        ArgumentCaptor<Map<String, Object>> updateCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper, org.mockito.Mockito.times(2)).updateApplication(updateCaptor.capture());
        assertThat(updateCaptor.getAllValues())
                .allSatisfy(update -> assertThat(update).containsEntry("status", "PROCESSING"));
        verify(flowMapper, org.mockito.Mockito.times(2)).insertApprovalLog(any());
        verify(flowMapper, never()).lockAssets(any());
    }

    @Test
    void shouldRejectDuplicateApplicationsBeforeWriting() {
        assertThatThrownBy(
                        () ->
                                service.batchDecide(
                                        new AssetRequests.BatchDecision(
                                                List.of(63L, 63L),
                                                AssetRequests.DecisionAction.REJECT,
                                                "重复"),
                                        actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("审批申请不能重复");

        verifyNoInteractions(flowMapper, principalService, notificationService);
    }

    @Test
    void shouldRequireRemarkWhenBatchRejecting() {
        assertThatThrownBy(
                        () ->
                                service.batchDecide(
                                        new AssetRequests.BatchDecision(
                                                List.of(63L, 66L),
                                                AssetRequests.DecisionAction.REJECT,
                                                "   "),
                                        actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("请填写拒绝原因");

        verifyNoInteractions(flowMapper, principalService, notificationService);
    }

    @Test
    void shouldKeepTheWholeBatchInsideOneTransaction() throws Exception {
        assertThat(
                        AssetApprovalDecisionService.class
                                .getMethod(
                                        "batchDecide",
                                        AssetRequests.BatchDecision.class,
                                        CurrentUser.class)
                                .getAnnotation(Transactional.class))
                .isNotNull();
    }

    @Test
    void shouldRejectProcessingApplicationWhenCurrentUserIsItsHandler() {
        when(flowMapper.lockApplication(63L)).thenReturn(63L);
        when(flowMapper.findApplications(63L, null, false))
                .thenReturn(List.of(processingApplication(63L)));
        when(flowMapper.updateApplication(any())).thenReturn(1);

        service.decide(63L, false, "无法满足当前办理条件", actor);

        ArgumentCaptor<Map<String, Object>> updateCaptor = ArgumentCaptor.forClass(Map.class);
        verify(flowMapper).updateApplication(updateCaptor.capture());
        assertThat(updateCaptor.getValue())
                .containsEntry("expectedStatus", "PROCESSING")
                .containsEntry("status", "REJECTED")
                .containsEntry("remark", "无法满足当前办理条件");
        verify(flowMapper).insertApprovalLog(any());
        verifyNoInteractions(principalService);
    }

    @Test
    void shouldRejectProcessingRejectionWithoutReason() {
        when(flowMapper.lockApplication(63L)).thenReturn(63L);
        when(flowMapper.findApplications(63L, null, false))
                .thenReturn(List.of(processingApplication(63L)));

        assertThatThrownBy(() -> service.decide(63L, false, "   ", actor))
                .isInstanceOf(BusinessException.class)
                .hasMessage("请填写拒绝原因");

        verify(flowMapper, never()).updateApplication(any());
        verify(flowMapper, never()).insertApprovalLog(any());
    }

    @Test
    void shouldRejectProcessingRejectionByAnotherUser() {
        when(flowMapper.lockApplication(63L)).thenReturn(63L);
        when(flowMapper.findApplications(63L, null, false))
                .thenReturn(List.of(processingApplication(63L)));
        CurrentUser otherUser = new CurrentUser(11L, "session", "其他用户", List.of());

        assertThatThrownBy(() -> service.decide(63L, false, "无法满足当前办理条件", otherUser))
                .isInstanceOf(BusinessException.class)
                .hasMessage("您不是该流程的办理人");

        verify(flowMapper, never()).updateApplication(any());
        verify(flowMapper, never()).insertApprovalLog(any());
    }

    private Map<String, Object> application(long id) {
        Map<String, Object> application = new LinkedHashMap<>();
        application.put("id", id);
        application.put("status", "PENDING");
        application.put("title", "像素申请");
        application.put("requesterId", 30L);
        application.put("currentNodeIndex", 0);
        application.put(
                "nodes",
                "[{\"name\":\"业务负责人审批\",\"approverType\":\"USERS\","
                        + "\"approverIds\":[10],\"approverId\":10,\"approverName\":\"审批人\","
                        + "\"handlerId\":20,\"handlerName\":\"办理人\"}]");
        return application;
    }

    private Map<String, Object> processingApplication(long id) {
        Map<String, Object> application = application(id);
        application.put("status", "PROCESSING");
        application.put("handlerName", actor.displayName());
        application.put(
                "nodes",
                "[{\"name\":\"业务负责人审批\",\"approverType\":\"USERS\","
                        + "\"approverIds\":[10],\"approverId\":10,\"approverName\":\"审批人\","
                        + "\"handlerId\":10,\"handlerName\":\"办理人\"}]");
        return application;
    }
}
