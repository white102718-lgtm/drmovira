package com.adpulse.main.task.service;

import static org.assertj.core.api.Assertions.assertThat;
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
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 任务角色权限和状态迁移测试。 */
@ExtendWith(MockitoExtension.class)
@Disabled("投放任务已迁移到投放负责人分配投手流程；旧单负责人流程用例待删除")
class TaskServiceTest {
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
        authenticate(9L, "创建者");
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldRejectConfirmationByNonOwner() {
        when(mapper.findTaskForUpdate(1L))
                .thenReturn(task(1L, "DELIVERY", "PENDING_CONFIRMATION", 9L, 10L));

        assertThatThrownBy(() -> service.confirm(1L))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("负责人");
    }

    @Test
    void shouldConfirmByOwnerWithOptimisticVersion() {
        authenticate(10L, "负责人");
        when(mapper.findTaskForUpdate(1L))
                .thenReturn(task(1L, "DELIVERY", "PENDING_CONFIRMATION", 9L, 10L));
        when(mapper.confirmTask(eq(1L), eq(10L), eq(0), any(LocalDateTime.class))).thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task(1L, "DELIVERY", "PROCESSING", 9L, 10L));
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.confirm(1L);

        verify(mapper).confirmTask(eq(1L), eq(10L), eq(0), any(LocalDateTime.class));
    }

    @Test
    void shouldDeclinePendingConfirmationByOwnerWithReason() {
        authenticate(10L, "负责人");
        when(mapper.findTaskForUpdate(1L))
                .thenReturn(task(1L, "DELIVERY", "PENDING_CONFIRMATION", 9L, 10L));
        when(mapper.declineTask(eq(1L), eq(10L), eq(0), eq("排期冲突"), any(LocalDateTime.class)))
                .thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task(1L, "DELIVERY", "REJECTED", 9L, 10L));
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.decline(1L, new TaskRequests.Decline("排期冲突"));

        verify(mapper).declineTask(eq(1L), eq(10L), eq(0), eq("排期冲突"), any(LocalDateTime.class));
    }

    @Test
    void shouldWithdrawPendingAssignmentByCreator() {
        when(mapper.findTaskForUpdate(1L))
                .thenReturn(task(1L, "DELIVERY", "PENDING_ASSIGNMENT", 9L, null));
        when(mapper.withdrawTask(eq(1L), eq(9L), eq(0), eq("需求取消"), any(LocalDateTime.class)))
                .thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task(1L, "DELIVERY", "WITHDRAWN", 9L, null));
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.withdraw(1L, new TaskRequests.Withdraw("需求取消"));

        verify(mapper).withdrawTask(eq(1L), eq(9L), eq(0), eq("需求取消"), any(LocalDateTime.class));
    }

    @Test
    void shouldResubmitFailedTaskByCreatorToPendingAssignment() {
        when(mapper.findTaskForUpdate(1L)).thenReturn(task(1L, "DELIVERY", "REJECTED", 9L, 10L));
        when(mapper.resubmitTask(eq(1L), eq(9L), eq(0), any(LocalDateTime.class))).thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task(1L, "DELIVERY", "PENDING_ASSIGNMENT", 9L, null));
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.resubmit(1L);

        verify(mapper).resubmitTask(eq(1L), eq(9L), eq(0), any(LocalDateTime.class));
    }

    @Test
    void shouldAssignPendingTaskByCreator() {
        when(mapper.findTaskForUpdate(1L))
                .thenReturn(task(1L, "DELIVERY", "PENDING_ASSIGNMENT", 9L, null));
        when(mapper.findActiveUserName(10L)).thenReturn("负责人");
        when(mapper.assignTask(
                        eq(1L),
                        eq(9L),
                        eq(10L),
                        eq("负责人"),
                        eq(9L),
                        eq("创建者"),
                        any(LocalDateTime.class),
                        eq(0)))
                .thenReturn(1);
        when(mapper.findTask(1L)).thenReturn(task(1L, "DELIVERY", "PENDING_CONFIRMATION", 9L, 10L));
        when(mapper.findDeliveryPlatforms(1L)).thenReturn(List.of());
        when(mapper.findAllocations(1L)).thenReturn(List.of());
        when(mapper.findTaskFiles(1L)).thenReturn(List.of());
        when(mapper.findDeliverySubmissions(1L)).thenReturn(List.of());

        service.assign(1L, new TaskRequests.Assign("10"));

        verify(mapper)
                .assignTask(
                        eq(1L),
                        eq(9L),
                        eq(10L),
                        eq("负责人"),
                        eq(9L),
                        eq("创建者"),
                        any(LocalDateTime.class),
                        eq(0));
    }

    @Test
    void shouldPersistFollowForVisibleTask() {
        when(mapper.findTask(1L)).thenReturn(task(1L, "MATERIAL", "PROCESSING", 9L, 10L));
        when(mapper.countTaskFollow(1L, 9L)).thenReturn(0);

        service.follow(1L);

        verify(mapper).insertTaskFollow(1L, 9L);
    }

    @Test
    void shouldRequireReasonWhenRejectingSubmission() {
        assertThatThrownBy(() -> service.reject(1L, 2L, "delivery", new TaskRequests.Review("  ")))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("原因");
    }

    @Test
    void shouldRejectDuplicateDeliveryTeams() {
        TaskRequests.BaseCreate base =
                new TaskRequests.BaseCreate(
                        "测试投放任务", "说明", "1", "10", "P2", LocalDateTime.now().plusDays(1));
        TaskRequests.DeliveryCreate request =
                new TaskRequests.DeliveryCreate(
                        base,
                        "https://example.com",
                        "US",
                        "获取用户",
                        LocalDateTime.now().plusHours(1),
                        List.of("FACEBOOK"),
                        List.of(),
                        null,
                        List.of());
        when(mapper.findProjectName(1L)).thenReturn("项目");
        when(mapper.findActiveUserName(10L)).thenReturn("负责人");
        when(mapper.countEnabledDictionaryValues("TASK_PRIORITY", List.of("P2"))).thenReturn(1);
        assertThatThrownBy(() -> service.createDelivery(request))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("不能重复");
    }

    @Test
    void shouldRequireAmRoleForDeliveryCreation() throws NoSuchMethodException {
        PreAuthorize annotation =
                TaskService.class
                        .getMethod("createDelivery", TaskRequests.DeliveryCreate.class)
                        .getAnnotation(PreAuthorize.class);

        org.assertj.core.api.Assertions.assertThat(annotation).isNotNull();
        org.assertj.core.api.Assertions.assertThat(annotation.value()).isEqualTo("hasRole('AM')");
    }

    @Test
    void shouldRecordCreatorAsAssignerWhenDeliveryOwnerIsSelected() {
        stubDeliveryCreation("10");

        service.createDelivery(deliveryRequest("10"));

        ArgumentCaptor<TaskModels.Task> taskCaptor = ArgumentCaptor.forClass(TaskModels.Task.class);
        verify(mapper).insertTask(taskCaptor.capture());
        TaskModels.Task task = taskCaptor.getValue();
        assertThat(task.getStatus()).isEqualTo("PENDING_CONFIRMATION");
        assertThat(task.getAssignerId()).isEqualTo(9L);
        assertThat(task.getAssignerName()).isEqualTo("创建者");
    }

    @Test
    void shouldKeepAssignerEmptyWhenDeliveryOwnerIsNotSelected() {
        stubDeliveryCreation(null);

        service.createDelivery(deliveryRequest(null));

        ArgumentCaptor<TaskModels.Task> taskCaptor = ArgumentCaptor.forClass(TaskModels.Task.class);
        verify(mapper).insertTask(taskCaptor.capture());
        TaskModels.Task task = taskCaptor.getValue();
        assertThat(task.getStatus()).isEqualTo("PENDING_ASSIGNMENT");
        assertThat(task.getAssignerId()).isNull();
        assertThat(task.getAssignerName()).isNull();
    }

    @Test
    void shouldAllowDeliveryCreationWithoutDueAt() {
        stubDeliveryCreation("10");
        TaskRequests.DeliveryCreate request = deliveryRequest("10", null);

        service.createDelivery(request);

        ArgumentCaptor<TaskModels.Task> taskCaptor = ArgumentCaptor.forClass(TaskModels.Task.class);
        verify(mapper).insertTask(taskCaptor.capture());
        assertThat(taskCaptor.getValue().getDueAt()).isNull();
    }

    @Test
    void shouldAllowDeliveryCreationWithoutProductUrl() {
        stubDeliveryCreation("10");

        service.createDelivery(deliveryRequest("10", LocalDateTime.now().plusDays(1), ""));

        ArgumentCaptor<TaskModels.DeliveryDetail> detailCaptor =
                ArgumentCaptor.forClass(TaskModels.DeliveryDetail.class);
        verify(mapper).insertDeliveryDetail(detailCaptor.capture());
        assertThat(detailCaptor.getValue().getProductUrl()).isEmpty();
    }

    private void stubDeliveryCreation(String ownerId) {
        when(mapper.findActiveDeliveryDepartment(100L)).thenReturn("投放部");
        when(mapper.findProjectName(1L)).thenReturn("项目");
        when(mapper.countEnabledDictionaryValues("TASK_PRIORITY", List.of("P2"))).thenReturn(1);
        when(mapper.findActiveUserName(11L)).thenReturn("团队负责人");
        if (ownerId != null) when(mapper.findActiveUserName(10L)).thenReturn("任务负责人");
    }

    @Test
    void shouldPersistDepartmentIdAsDeliveryTeam() {
        stubDeliveryCreation(null);
        service.createDelivery(deliveryRequest(null));
        ArgumentCaptor<TaskModels.Allocation> allocation =
                ArgumentCaptor.forClass(TaskModels.Allocation.class);
        verify(mapper).insertAllocation(allocation.capture());
        assertThat(allocation.getValue().getTeamCode()).isEqualTo("100");
    }

    @Test
    void shouldRejectMissingOrInactiveDepartmentOnCreation() {
        when(mapper.findProjectName(1L)).thenReturn("项目");
        when(mapper.countEnabledDictionaryValues("TASK_PRIORITY", List.of("P2"))).thenReturn(1);
        assertThatThrownBy(() -> service.createDelivery(deliveryRequest(null)))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("参与部门");
        verify(mapper, org.mockito.Mockito.never()).insertAllocation(any());
    }

    @Test
    void shouldRejectInactiveDepartmentOnResubmission() {
        when(mapper.findTaskForUpdate(1L)).thenReturn(task(1L, "DELIVERY", "REJECTED", 9L, 10L));
        assertThatThrownBy(() -> service.resubmitDelivery(1L, deliveryRequest(null)))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("参与部门");
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.NullAndEmptySource
    @org.junit.jupiter.params.provider.ValueSource(
            strings = {"MP", "0", "0100", "-1", "100 OR 1=1"})
    void shouldRequireCanonicalDepartmentId(String team) {
        when(mapper.findTaskForUpdate(1L)).thenReturn(task(1L, "DELIVERY", "REJECTED", 9L, 10L));
        TaskRequests.DeliveryCreate original = deliveryRequest(null);
        TaskRequests.DeliveryCreate request =
                new TaskRequests.DeliveryCreate(
                        original.task(),
                        original.productUrl(),
                        original.region(),
                        original.target(),
                        original.plannedStartAt(),
                        original.platforms(),
                        original.files(),
                        null,
                        List.of());
        assertThatThrownBy(() -> service.resubmitDelivery(1L, request))
                .isInstanceOf(TaskService.TaskException.class)
                .hasMessageContaining("参与部门");
    }

    private TaskRequests.DeliveryCreate deliveryRequest(String ownerId) {
        return deliveryRequest(ownerId, LocalDateTime.now().plusDays(1));
    }

    private TaskRequests.DeliveryCreate deliveryRequest(String ownerId, LocalDateTime dueAt) {
        return deliveryRequest(ownerId, dueAt, "https://example.com");
    }

    private TaskRequests.DeliveryCreate deliveryRequest(
            String ownerId, LocalDateTime dueAt, String productUrl) {
        return new TaskRequests.DeliveryCreate(
                new TaskRequests.BaseCreate("测试投放任务", "说明", "1", ownerId, "P2", dueAt),
                productUrl,
                "US",
                "获取用户",
                LocalDateTime.now().plusHours(1),
                List.of("FACEBOOK"),
                List.of(),
                null,
                List.of());
    }

    private void authenticate(Long userId, String name) {
        CurrentUser user = new CurrentUser(userId, "session", name, List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }

    private TaskModels.Task task(
            Long id, String type, String status, Long creatorId, Long ownerId) {
        TaskModels.Task task = new TaskModels.Task();
        task.setId(id);
        task.setTaskType(type);
        task.setStatus(status);
        task.setCreatorId(creatorId);
        task.setCreatorName("创建者");
        task.setOwnerId(ownerId);
        task.setOwnerName("负责人");
        task.setVersion(0);
        return task;
    }
}
