package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.AssetApplication;
import com.adpulse.system.asset.model.AssetApplicationComment;
import com.adpulse.system.common.exception.BusinessException;
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

/** 审批流程评论参与人权限与持久化测试。 */
@ExtendWith(MockitoExtension.class)
class AssetApprovalCommentServiceTest {

    @Mock private AssetMapper mapper;
    @Mock private AssetApprovalPrincipalService principalService;

    private AssetApprovalCommentService service;

    @BeforeEach
    void setUp() {
        CurrentUser user = new CurrentUser(7L, "session", "测试申请人", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        service = new AssetApprovalCommentService(mapper, new ObjectMapper(), principalService);
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldPersistRequesterCommentWithServerRole() {
        AssetApplication application = application(7L);
        when(mapper.findApplication(31L)).thenReturn(application);
        when(mapper.insertApplicationComment(any(AssetApplicationComment.class)))
                .thenAnswer(
                        invocation -> {
                            AssetApplicationComment comment = invocation.getArgument(0);
                            comment.setId(91L);
                            return 1;
                        });
        AssetApplicationComment stored = new AssetApplicationComment();
        stored.setId(91L);
        stored.setApplicationId(31L);
        stored.setActorId(7L);
        stored.setActorName("测试申请人");
        stored.setActorRole("申请人");
        stored.setContent("请优先处理");
        stored.setCreatedAt(LocalDateTime.of(2026, 8, 20, 22, 0));
        when(mapper.findApplicationComment(91L)).thenReturn(stored);

        var result = service.comment(31L, new AssetRequests.ApprovalCommentCreate(" 请优先处理 "));

        assertThat(result.actorRole()).isEqualTo("申请人");
        assertThat(result.content()).isEqualTo("请优先处理");
        verify(mapper).insertApplicationComment(any(AssetApplicationComment.class));
    }

    @Test
    void shouldRejectUnrelatedUser() {
        when(mapper.findApplication(31L)).thenReturn(application(99L));

        assertThatThrownBy(() -> service.comments(31L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("当前用户不是该审批流程参与人");
    }

    @Test
    void shouldPreferApproverRoleWhenRequesterIsAlsoApprover() {
        AssetApplication application = application(7L);
        application.setStatus("PENDING");
        application.setApproverId(7L);
        when(mapper.findApplication(31L)).thenReturn(application);
        when(mapper.insertApplicationComment(any(AssetApplicationComment.class)))
                .thenAnswer(
                        invocation -> {
                            AssetApplicationComment comment = invocation.getArgument(0);
                            assertThat(comment.getActorRole()).isEqualTo("审批人");
                            comment.setId(92L);
                            return 1;
                        });
        AssetApplicationComment stored = new AssetApplicationComment();
        stored.setId(92L);
        stored.setActorRole("审批人");
        stored.setActorName("测试申请人");
        stored.setContent("审批意见补充");
        stored.setCreatedAt(LocalDateTime.of(2026, 8, 21, 10, 0));
        when(mapper.findApplicationComment(92L)).thenReturn(stored);

        var result = service.comment(31L, new AssetRequests.ApprovalCommentCreate("审批意见补充"));

        assertThat(result.actorRole()).isEqualTo("审批人");
    }

    @Test
    void shouldAllowRoleMemberToReadApprovalComments() {
        AssetApplication application = application(99L);
        application.setNodesSnapshot("[{\"approverType\":\"ROLES\",\"roleIds\":[\"1\"]}]");
        when(mapper.findApplication(31L)).thenReturn(application);
        when(principalService.canApprove(anyMap(), eq(7L))).thenReturn(true);
        when(mapper.findApplicationComments(31L)).thenReturn(List.of());

        assertThat(service.comments(31L)).isEmpty();
        verify(principalService).canApprove(anyMap(), eq(7L));
    }

    @Test
    void shouldReturnOnlyParticipantApplicationSummaries() {
        AssetApplication visible = application(7L);
        visible.setStatus("PROCESSING");
        visible.setRequesterName("测试申请人");
        AssetApplication hidden = application(99L);
        hidden.setId(32L);
        hidden.setStatus("PENDING");
        hidden.setRequesterName("其他申请人");
        when(mapper.findApplicationsByIds(List.of(31L, 32L))).thenReturn(List.of(visible, hidden));

        var result = service.applicationSummaries(List.of(31L, 32L));

        assertThat(result)
                .containsExactly(new AssetViews.ApplicationSummary("31", "PROCESSING", "测试申请人"));
    }

    private AssetApplication application(Long requesterId) {
        AssetApplication application = new AssetApplication();
        application.setId(31L);
        application.setRequesterId(requesterId);
        application.setApproverId(8L);
        application.setFormData("{}");
        application.setNodesSnapshot("[]");
        return application;
    }
}
