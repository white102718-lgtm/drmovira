package com.adpulse.main.task.service;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.task.dto.TaskRequests;
import com.adpulse.main.task.mapper.TaskMapper;
import com.adpulse.main.task.model.TaskModels;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 投放负责人分配投手的权限与边界测试。 */
@ExtendWith(MockitoExtension.class)
class DeliveryAllocationWorkflowTest {
    @Mock private TaskMapper mapper;
    private TaskService service;

    @BeforeEach
    void setUp() {
        service =
                new TaskService(
                        mapper,
                        new ObjectMapper(),
                        org.mockito.Mockito.mock(
                                com.adpulse.main.integration.security.IntegrationSecretCipher
                                        .class),
                        org.mockito.Mockito.mock(
                                com.adpulse.main.task.mongo.MongoMaterialTaskQueryProvider.class));
        org.mockito.Mockito.lenient()
                .when(mapper.findDeliveryAgencyLinesByIds(any()))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.task.dto.TaskViews.AgencyLineOption(
                                        "21", "代理线")));
        authenticate(10L, "投放负责人");
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldRejectRetiredAssignmentEndpoint() {
        assertThatThrownBy(
                        () ->
                                service.assignDeliveryAllocations(
                                        1L,
                                        new TaskRequests.DeliveryAllocationAssign(
                                                List.of(
                                                        new TaskRequests.Allocation(
                                                                "100", "11", 1, 0)))))
                .hasMessageContaining("独立分配已停用");
    }

    @Test
    void shouldRequireFormWhenResubmittingDelivery() {
        when(mapper.findTaskForUpdate(1L)).thenReturn(task());
        assertThatThrownBy(() -> service.resubmit(1L)).hasMessageContaining("通过表单重新提交");
    }

    @Test
    void shouldRejectEmptyItemsBeforeCreatingTask() {
        assertThatThrownBy(
                        () ->
                                service.createDelivery(
                                        new TaskRequests.DeliveryCreate(
                                                null,
                                                "",
                                                "",
                                                "",
                                                LocalDateTime.now(),
                                                List.of(),
                                                List.of(),
                                                null,
                                                List.of())))
                .hasMessageContaining("投放明细");
    }

    @Test
    void shouldAllowDeliveryLeaderToDeclinePendingConfirmation() {
        when(mapper.findTaskForUpdate(1L)).thenReturn(task());
        when(mapper.declineTask(eq(1L), eq(10L), eq(0), eq("暂不承接"), any())).thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task());
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.decline(1L, new TaskRequests.Decline("暂不承接"));

        verify(mapper).declineTask(eq(1L), eq(10L), eq(0), eq("暂不承接"), any());
    }

    @Test
    void shouldListUnassignedDeliveryTasksForDeliveryLeader() {
        when(mapper.findTasks(
                        eq(10L),
                        eq("PENDING_ASSIGNMENT"),
                        eq("DELIVERY"),
                        eq(null),
                        eq(null),
                        eq(0),
                        eq(20)))
                .thenReturn(List.of(task()));
        when(mapper.countTasks(
                        eq(10L), eq("PENDING_ASSIGNMENT"), eq("DELIVERY"), eq(null), eq(null)))
                .thenReturn(1L);

        service.list("DELIVERY", null, null, "PENDING_ASSIGNMENT", 1, 20);

        verify(mapper)
                .findTasks(
                        eq(10L),
                        eq("PENDING_ASSIGNMENT"),
                        eq("DELIVERY"),
                        eq(null),
                        eq(null),
                        eq(0),
                        eq(20));
    }

    @Test
    void shouldRestoreConfiguredDeliveryLeaderWhenResubmitting() {
        TaskModels.Task rejectedTask = task();
        rejectedTask.setStatus("REJECTED");
        authenticate(9L, "AM");
        TaskModels.ProjectTaskOwners projectOwners = new TaskModels.ProjectTaskOwners();
        projectOwners.setDeliveryLeaderId(10L);
        projectOwners.setDeliveryLeaderName("投放负责人");
        when(mapper.findTaskForUpdate(1L)).thenReturn(rejectedTask);
        when(mapper.findProjectName(1L)).thenReturn("测试项目");
        when(mapper.findProjectTaskOwners(1L)).thenReturn(projectOwners);
        TaskModels.UserSnapshot firstAm = new TaskModels.UserSnapshot();
        firstAm.setUserId(20L);
        firstAm.setUserName("AM甲");
        TaskModels.UserSnapshot secondAm = new TaskModels.UserSnapshot();
        secondAm.setUserId(21L);
        secondAm.setUserName("AM乙");
        when(mapper.findProjectAms(1L)).thenReturn(List.of(firstAm, secondAm));
        when(mapper.findActiveUserName(10L)).thenReturn("投放负责人");
        when(mapper.countEnabledDictionaryValues("TASK_PRIORITY", List.of("P2"))).thenReturn(1);
        when(mapper.updateDeliveryTaskForResubmit(
                        eq(1L),
                        eq(9L),
                        eq(1L),
                        eq("重新提交投放任务"),
                        eq(null),
                        eq(10L),
                        eq("投放负责人"),
                        eq("P2"),
                        eq(null),
                        eq(0),
                        any()))
                .thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(rejectedTask);
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.resubmitDelivery(
                1L,
                new TaskRequests.DeliveryCreate(
                        new TaskRequests.BaseCreate("重新提交投放任务", null, "1", null, "P2", null),
                        "https://example.com/product",
                        "US",
                        "重新提交目标",
                        LocalDateTime.now().plusDays(1),
                        List.of("FACEBOOK"),
                        List.of(),
                        null,
                        List.of(
                                new TaskRequests.DeliveryItem(
                                        "PWA",
                                        "像素",
                                        "123",
                                        "test-secret",
                                        "code",
                                        "代理线",
                                        "https://example.com",
                                        "10",
                                        "",
                                        null,
                                        "21",
                                        "代理线"))));

        verify(mapper)
                .updateDeliveryTaskForResubmit(
                        eq(1L),
                        eq(9L),
                        eq(1L),
                        eq("重新提交投放任务"),
                        eq(null),
                        eq(10L),
                        eq("投放负责人"),
                        eq("P2"),
                        eq(null),
                        eq(0),
                        any());
        verify(mapper).deleteDeliveryTaskAms(eq(1L), any(Long.class));
        verify(mapper).insertDeliveryTaskAm(1L, 20L, "AM甲", 0, 9L);
        verify(mapper).insertDeliveryTaskAm(1L, 21L, "AM乙", 1, 9L);
    }

    private TaskModels.Task task() {
        TaskModels.Task task = new TaskModels.Task();
        task.setId(1L);
        task.setTaskType("DELIVERY");
        task.setStatus("PENDING_CONFIRMATION");
        task.setCreatorId(9L);
        task.setOwnerId(10L);
        task.setOwnerName("投放负责人");
        task.setVersion(0);
        return task;
    }

    private void authenticate(Long id, String name) {
        CurrentUser user = new CurrentUser(id, "session", name, List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }
}
