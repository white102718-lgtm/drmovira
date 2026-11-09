package com.adpulse.main.task.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.task.dto.TaskRequests;
import com.adpulse.main.task.mapper.TaskMapper;
import com.adpulse.main.task.model.TaskModels;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.config.SecurityProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 创建时分配、负责人确认及令牌存储的业务边界。 */
@ExtendWith(MockitoExtension.class)
class DeliveryCreationWorkflowTest {
    @Mock private TaskMapper mapper;
    private final ObjectMapper json = new ObjectMapper();
    private IntegrationSecretCipher cipher;
    private TaskService service;

    @BeforeEach
    void setUp() {
        SecurityProperties properties = mock(SecurityProperties.class);
        when(properties.jwtSecret()).thenReturn("unit-test-secret-not-a-real-credential");
        cipher = new IntegrationSecretCipher(properties);
        service =
                new TaskService(
                        mapper,
                        json,
                        cipher,
                        org.mockito.Mockito.mock(
                                com.adpulse.main.task.mongo.MongoMaterialTaskQueryProvider.class));
        org.mockito.Mockito.lenient()
                .when(mapper.findDeliveryAgencyLinesByIds(any()))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.task.dto.TaskViews.AgencyLineOption(
                                        "21", "代理线")));
        authenticate(9L);
    }

    @AfterEach
    void clearAuthentication() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldSearchAgencyLinesInBoundedPages() {
        service.deliveryAgencyLines(" 测试 ", 2);
        verify(mapper).findDeliveryAgencyLines("测试", 30, 30);
        assertThatThrownBy(() -> service.deliveryAgencyLines("", 0)).hasMessageContaining("参数");
    }

    @Test
    void shouldOnlyMatchImportedAgencyLineNames() {
        service.matchDeliveryAgencyLines(List.of("代理线一", " 代理线一 ", "代理线二"));
        verify(mapper).findDeliveryAgencyLinesByNames(List.of("代理线一", "代理线二"));
        assertThatThrownBy(() -> service.matchDeliveryAgencyLines(List.of(" ")))
                .hasMessageContaining("有效代理线");
        assertThatThrownBy(
                        () ->
                                service.matchDeliveryAgencyLines(
                                        java.util.Collections.nCopies(1001, "代理线")))
                .hasMessageContaining("1000");
    }

    @Test
    void shouldCreatePendingConfirmationAndGroupRepeatedOperator() {
        when(mapper.findDeliveryAgencyLinesByIds(any()))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.task.dto.TaskViews.AgencyLineOption(
                                        "21", "系统最新代理线名称")));
        when(mapper.findProjectName(1L)).thenReturn("项目");
        when(mapper.findActiveUserName(10L)).thenReturn("负责人");
        when(mapper.findActiveUserName(11L)).thenReturn("投手");
        when(mapper.countEnabledDictionaryValues("TASK_PRIORITY", List.of("P1"))).thenReturn(1);
        doAnswer(
                        call -> {
                            ((TaskModels.Task) call.getArgument(0)).setId(1L);
                            return 1;
                        })
                .when(mapper)
                .insertTask(any());

        service.createDelivery(request(List.of(item("11"), item("11"))));

        var task = ArgumentCaptor.forClass(TaskModels.Task.class);
        verify(mapper).insertTask(task.capture());
        assertThat(task.getValue().getStatus()).isEqualTo("PENDING_CONFIRMATION");
        assertThat(task.getValue().getAssignerId()).isEqualTo(9L);
        var allocation = ArgumentCaptor.forClass(TaskModels.Allocation.class);
        verify(mapper, times(1)).insertAllocation(allocation.capture());
        assertThat(allocation.getValue().getTeamOwnerId()).isEqualTo(11L);
        var detail = ArgumentCaptor.forClass(TaskModels.DeliveryDetail.class);
        verify(mapper).insertDeliveryDetail(detail.capture());
        assertThat(detail.getValue().getItemsCiphertext()).doesNotContain("test-token");
        assertThat(cipher.decrypt(detail.getValue().getItemsCiphertext()))
                .contains("test-token", "9007199254740993", "系统最新代理线名称", "\"agencyLineId\":\"21\"");
    }

    @Test
    void shouldRejectUnknownOrDeletedChannelBeforeWriting() {
        when(mapper.findActiveUserName(11L)).thenReturn("投手");
        when(mapper.findDeliveryAgencyLinesByIds(any())).thenReturn(List.of());
        assertThatThrownBy(() -> service.createDelivery(request(List.of(item("11")))))
                .hasMessageContaining("第 1 行代理线不存在");
        verify(mapper, never()).insertTask(any());
    }

    @Test
    void shouldRequireExplicitAgencyLineForLegacyChannel() {
        assertThatThrownBy(() -> service.createDelivery(request(List.of(item("11", null)))))
                .hasMessageContaining("历史渠道明细请重新选择代理线");
        verify(mapper, never()).insertTask(any());
    }

    @Test
    void shouldRejectMissingOperatorBeforeWriting() {
        assertThatThrownBy(() -> service.createDelivery(request(List.of(item("")))))
                .hasMessageContaining("每行必须指定投手");
        verify(mapper, never()).insertTask(any());
    }

    @Test
    void shouldRejectDisabledOperatorBeforeWriting() {
        assertThatThrownBy(() -> service.createDelivery(request(List.of(item("11")))))
                .hasMessageContaining("投手");
        verify(mapper, never()).insertTask(any());
    }

    @Test
    void shouldPreventOperatorFromConfirmingTask() {
        authenticate(11L);
        when(mapper.findTaskForUpdate(1L)).thenReturn(task("PENDING_CONFIRMATION"));
        assertThatThrownBy(() -> service.confirm(1L)).hasMessageContaining("只有任务负责人");
        verify(mapper, never()).confirmTask(any(), any(), anyInt(), any());
    }

    @Test
    void shouldAllowLeaderConfirmationAfterValidatingOperators() throws Exception {
        authenticate(10L);
        when(mapper.findTaskForUpdate(1L)).thenReturn(task("PENDING_CONFIRMATION"));
        when(mapper.findTask(1L)).thenReturn(task("PROCESSING"));
        when(mapper.findActiveUserName(11L)).thenReturn("投手");
        var detail = new TaskModels.DeliveryDetail();
        detail.setItemsCiphertext(cipher.encrypt(json.writeValueAsString(List.of(item("11")))));
        when(mapper.findDeliveryDetail(1L)).thenReturn(detail);
        when(mapper.confirmTask(eq(1L), eq(10L), eq(0), any())).thenReturn(1);
        assertThat(service.confirm(1L).task().status()).isEqualTo("PROCESSING");
    }

    @Test
    void shouldRejectConfirmationWhenAlreadyProcessing() {
        authenticate(10L);
        when(mapper.findTaskForUpdate(1L)).thenReturn(task("PROCESSING"));
        assertThatThrownBy(() -> service.confirm(1L)).hasMessageContaining("不可确认");
        verify(mapper, never()).confirmTask(any(), any(), anyInt(), any());
    }

    @Test
    void shouldKeepIncompleteDraftEncryptedAndRestoreIt() throws Exception {
        var payload = json.readTree("{\"items\":[{\"token\":\"test-token\",\"operatorId\":\"\"}]}");
        var saved = new TaskModels.Draft();
        doAnswer(
                        call -> {
                            var draft = (TaskModels.Draft) call.getArgument(0);
                            draft.setId(7L);
                            saved.setId(7L);
                            saved.setPayloadJson(draft.getPayloadJson());
                            return 1;
                        })
                .when(mapper)
                .insertDraft(any());
        when(mapper.findDraft(7L)).thenReturn(saved);
        var result =
                service.createDraft(new TaskRequests.DraftSave("DELIVERY", "草稿", null, payload));
        assertThat(saved.getPayloadJson()).doesNotContain("test-token");
        assertThat(result.payload()).isEqualTo(payload);
    }

    @Test
    void shouldOnlyReturnOwnItemsToOperatorEvenWhenFollowingTask() throws Exception {
        prepareVisibilityTask();
        authenticate(11L);
        lenient().when(mapper.countTaskFollow(1L, 11L)).thenReturn(1);
        assertThat(service.get(1L).delivery().items())
                .extracting(TaskRequests.DeliveryItem::operatorId)
                .containsExactly("11");
        authenticate(12L);
        assertThat(service.get(1L).delivery().items())
                .extracting(TaskRequests.DeliveryItem::operatorId)
                .containsExactly("12");
    }

    @Test
    void shouldKeepAllItemsForManagersAmAndOtherAuthorizedViewers() throws Exception {
        prepareVisibilityTask();
        when(mapper.countTaskFollow(1L, 15L)).thenReturn(1);
        // 13 同时是 AM 和投手，应按 AM 权限查看完整明细。
        lenient().when(mapper.countAllocationForOperator(1L, 13L)).thenReturn(1);
        for (long userId : new long[] {9L, 10L, 13L, 14L, 15L}) {
            authenticate(userId);
            assertThat(service.get(1L).delivery().items()).hasSize(2);
        }
    }

    @Test
    void shouldRejectUnrelatedViewer() throws Exception {
        prepareVisibilityTask();
        authenticate(16L);
        assertThatThrownBy(() -> service.get(1L)).hasMessageContaining("没有权限");
    }

    private void prepareVisibilityTask() throws Exception {
        var task = task("PROCESSING");
        task.setAssignerId(14L);
        when(mapper.findTask(1L)).thenReturn(task);
        var detail = new TaskModels.DeliveryDetail();
        detail.setItemsCiphertext(
                cipher.encrypt(json.writeValueAsString(List.of(item("11"), item("12")))));
        lenient().when(mapper.findDeliveryDetail(1L)).thenReturn(detail);
        var am = new TaskModels.UserSnapshot();
        am.setUserId(13L);
        am.setUserName("AM");
        lenient().when(mapper.findDeliveryTaskAms(1L)).thenReturn(List.of(am));
        lenient().when(mapper.countAllocationForOperator(1L, 11L)).thenReturn(1);
        lenient().when(mapper.countAllocationForOperator(1L, 12L)).thenReturn(1);
    }

    private TaskRequests.DeliveryCreate request(List<TaskRequests.DeliveryItem> items) {
        return new TaskRequests.DeliveryCreate(
                new TaskRequests.BaseCreate("任务", null, "1", "10", "P1", null),
                "https://example.com",
                "US",
                "目标",
                LocalDateTime.now().plusDays(1),
                List.of("Facebook"),
                List.of(),
                null,
                items);
    }

    private TaskRequests.DeliveryItem item(String operator) {
        return item(operator, "21");
    }

    private TaskRequests.DeliveryItem item(String operator, String channelId) {
        return new TaskRequests.DeliveryItem(
                "PWA",
                "像素",
                "9007199254740993",
                "test-token",
                "code",
                "代理线",
                "https://example.com",
                operator,
                "",
                null,
                channelId,
                "代理线");
    }

    private TaskModels.Task task(String status) {
        var task = new TaskModels.Task();
        task.setId(1L);
        task.setTaskType("DELIVERY");
        task.setStatus(status);
        task.setCreatorId(9L);
        task.setOwnerId(10L);
        task.setVersion(0);
        return task;
    }

    private void authenticate(Long id) {
        var user = new CurrentUser(id, "session", "用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }
}
