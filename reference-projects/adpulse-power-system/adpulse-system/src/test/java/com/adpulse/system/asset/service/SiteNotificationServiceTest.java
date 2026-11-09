package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.SiteNotification;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
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

/** 站内通知分页与未读状态测试。 */
@ExtendWith(MockitoExtension.class)
class SiteNotificationServiceTest {
    @Mock private AssetMapper mapper;

    private SiteNotificationService service;

    @BeforeEach
    void setUp() {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        service = new SiteNotificationService(mapper);
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldReturnUnreadStatusWithoutLoadingNotificationList() {
        when(mapper.hasUnreadNotification(7L)).thenReturn(true);

        assertThat(service.unreadStatus().hasUnread()).isTrue();
        verify(mapper).hasUnreadNotification(7L);
    }

    @Test
    void shouldReturnNotificationPageWithStringIds() {
        SiteNotification notification = new SiteNotification();
        notification.setId(9_007_199_254_740_993L);
        notification.setTitle("待处理审批");
        notification.setContent("申请已到达当前节点");
        notification.setTargetPath("/workbench/approvals?id=1");
        notification.setBusinessType("APPROVAL");
        notification.setBusinessId(9_007_199_254_740_992L);
        notification.setRead(false);
        notification.setCreatedAt(LocalDateTime.of(2026, 8, 21, 10, 30));
        when(mapper.countNotifications(7L)).thenReturn(21L);
        when(mapper.findNotifications(7L, 0, 20)).thenReturn(List.of(notification));

        AssetViews.NotificationPage page = service.notifications(1, 20);

        assertThat(page.hasMore()).isTrue();
        assertThat(page.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.id()).isEqualTo("9007199254740993");
                            assertThat(item.businessId()).isEqualTo("9007199254740992");
                            assertThat(item.isRead()).isFalse();
                        });
    }

    @Test
    void shouldRejectInvalidPageSize() {
        assertThatThrownBy(() -> service.notifications(1, 101))
                .isInstanceOf(BusinessException.class)
                .hasMessage("每页条数必须在1到100之间");
    }
}
