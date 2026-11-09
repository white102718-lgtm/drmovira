package com.adpulse.system.feedback.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.feedback.dto.FeedbackRequests;
import com.adpulse.system.feedback.dto.FeedbackViews;
import com.adpulse.system.feedback.mapper.FeedbackMapper;
import com.adpulse.system.feedback.model.Feedback;
import com.adpulse.system.feedback.model.FeedbackUserSnapshot;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 反馈身份快照、诊断信息和附件引用校验测试。 */
@ExtendWith(MockitoExtension.class)
class FeedbackServiceTest {
    @Mock private FeedbackMapper mapper;

    private FeedbackService service;

    @BeforeEach
    void setUp() {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        service = new FeedbackService(mapper, new ObjectMapper());
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldCreateFeedbackWithServerAccountAndOwnedAttachments() {
        when(mapper.findUserSnapshot(7L)).thenReturn(new FeedbackUserSnapshot("tester", "测试用户"));
        when(mapper.findOwnedFileIds(List.of(11L, 12L), 7L)).thenReturn(List.of(11L, 12L));
        Feedback[] insertedFeedback = new Feedback[1];
        when(mapper.insertFeedback(any(Feedback.class)))
                .thenAnswer(
                        invocation -> {
                            Feedback feedback = invocation.getArgument(0);
                            feedback.setId(31L);
                            insertedFeedback[0] = feedback;
                            return 1;
                        });
        when(mapper.findFeedback(31L)).thenAnswer(invocation -> insertedFeedback[0]);
        when(mapper.findAttachments(31L)).thenReturn(List.of());

        FeedbackViews.Detail created =
                service.create(
                        new FeedbackRequests.Create(
                                "bug",
                                "页面报错",
                                "点击保存后没有响应",
                                List.of(11L, 12L),
                                new FeedbackRequests.Diagnostics(
                                        "1.0.0",
                                        "https://example.test/page?access_token=private-value",
                                        "Page",
                                        "zh-CN",
                                        "Asia/Shanghai",
                                        "desktop",
                                        "Windows",
                                        "Chrome",
                                        "1920×1080",
                                        "1440×900",
                                        1.0,
                                        8,
                                        16.0,
                                        "4g",
                                        List.of(
                                                new FeedbackRequests.ConsoleEntry(
                                                        "error",
                                                        "2026-08-21T07:23:58Z",
                                                        "request failed: Bearer private-token")))),
                        "203.0.113.8",
                        "Mozilla/5.0");

        assertThat(created.id()).isEqualTo("31");
        assertThat(created.submittedByUsername()).isEqualTo("tester");
        assertThat(created.diagnostics().get("deviceType").asText()).isEqualTo("desktop");
        assertThat(created.diagnostics().toString())
                .doesNotContain("private-value", "private-token");
        verify(mapper).insertAttachments(31L, List.of(11L, 12L), 7L);
    }

    @Test
    void shouldRejectAttachmentsThatAreNotOwnedByCurrentUser() {
        when(mapper.findUserSnapshot(7L)).thenReturn(new FeedbackUserSnapshot("tester", "测试用户"));
        when(mapper.findOwnedFileIds(List.of(11L, 12L), 7L)).thenReturn(List.of(11L));

        assertThatThrownBy(
                        () ->
                                service.create(
                                        new FeedbackRequests.Create(
                                                "FEATURE",
                                                "批量操作",
                                                "希望支持批量处理",
                                                List.of(11L, 12L),
                                                null),
                                        "203.0.113.8",
                                        "Mozilla/5.0"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("不属于当前账号");

        verify(mapper).findOwnedFileIds(eq(List.of(11L, 12L)), eq(7L));
    }

    @Test
    void shouldAssignActiveOwnerWhenUpdatingFeedback() {
        Feedback feedback = new Feedback();
        feedback.setId(31L);
        feedback.setCategory("FEATURE");
        feedback.setTitle("批量操作");
        feedback.setContent("希望支持批量处理");
        feedback.setStatus("PENDING");
        feedback.setSubmittedById(8L);
        feedback.setSubmittedByName("提交用户");
        when(mapper.findFeedback(31L)).thenReturn(feedback);
        when(mapper.findUserSnapshot(9L)).thenReturn(new FeedbackUserSnapshot("owner", "负责人"));
        when(mapper.updateStatus(31L, "PROCESSING", "已排期", 9L, "负责人", 7L, "测试用户")).thenReturn(1);
        when(mapper.findAttachments(31L)).thenReturn(List.of());

        service.updateStatus(31L, new FeedbackRequests.UpdateStatus("PROCESSING", 9L, "已排期"));

        verify(mapper).updateStatus(31L, "PROCESSING", "已排期", 9L, "负责人", 7L, "测试用户");
    }

    @Test
    void shouldRejectInactiveOwnerWhenUpdatingFeedback() {
        Feedback feedback = new Feedback();
        feedback.setId(31L);
        when(mapper.findFeedback(31L)).thenReturn(feedback);

        assertThatThrownBy(
                        () ->
                                service.updateStatus(
                                        31L,
                                        new FeedbackRequests.UpdateStatus("PROCESSING", 9L, null)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("负责人不存在或已停用");
    }

    @Test
    void shouldSummarizeFeedbackStatuses() {
        when(mapper.countFeedbacks(null, null, null)).thenReturn(12L);
        when(mapper.countFeedbacks(null, null, "PENDING")).thenReturn(3L);
        when(mapper.countFeedbacks(null, null, "PROCESSING")).thenReturn(4L);
        when(mapper.countFeedbacks(null, null, "RESOLVED")).thenReturn(4L);
        when(mapper.countFeedbacks(null, null, "CLOSED")).thenReturn(1L);

        FeedbackViews.Summary summary = service.summary();

        assertThat(summary).isEqualTo(new FeedbackViews.Summary(12L, 3L, 4L, 4L, 1L));
    }
}
