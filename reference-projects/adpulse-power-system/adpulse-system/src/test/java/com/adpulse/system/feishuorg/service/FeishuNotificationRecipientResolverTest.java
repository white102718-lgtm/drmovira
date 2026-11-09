package com.adpulse.system.feishuorg.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.feishuorg.client.FeishuOrganizationClient;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class FeishuNotificationRecipientResolverTest {
    private final FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
    private final FeishuOrganizationClient client = mock(FeishuOrganizationClient.class);

    @Test
    void testEnvironmentAlwaysUsesConfiguredRecipientAndPrefix() {
        FeishuNotificationRecipientResolver resolver =
                new FeishuNotificationRecipientResolver(mapper, client, "15362469449", "【测试环境】");
        when(mapper.findActiveFeishuOpenIdsByPhone("15362469449")).thenReturn(List.of("open-test"));

        assertThat(resolver.resolveOpenIds(List.of(12L))).containsExactly("open-test");
        assertThat(resolver.decorateContent("审批待处理")).isEqualTo("【测试环境】审批待处理");
        verify(mapper).findActiveFeishuOpenIdsByPhone("15362469449");
        verify(mapper, never()).findActiveFeishuOpenIds(List.of(12L));
        verify(client, never()).findOpenIdsByMobile("15362469449");
    }

    @Test
    void testEnvironmentFallsBackToFeishuMobileLookupWhenLocalSyncIsMissing() {
        FeishuNotificationRecipientResolver resolver =
                new FeishuNotificationRecipientResolver(mapper, client, "15362469449", "【测试环境】");
        when(mapper.findActiveFeishuOpenIdsByPhone("15362469449")).thenReturn(List.of());
        when(client.findOpenIdsByMobile("15362469449")).thenReturn(List.of("open-from-feishu"));

        assertThat(resolver.resolveOpenIds(List.of(12L))).containsExactly("open-from-feishu");
        verify(client).findOpenIdsByMobile("15362469449");
    }

    @Test
    void productionKeepsBusinessRecipientsAndOriginalContent() {
        FeishuNotificationRecipientResolver resolver =
                new FeishuNotificationRecipientResolver(mapper, client, "", "");
        when(mapper.findActiveFeishuOpenIds(List.of(12L))).thenReturn(List.of("open-business"));

        assertThat(resolver.resolveOpenIds(List.of(12L, 12L, -1L)))
                .containsExactly("open-business");
        assertThat(resolver.decorateContent("审批待处理")).isEqualTo("审批待处理");
        verify(mapper).findActiveFeishuOpenIds(List.of(12L));
        verify(mapper, never()).findActiveFeishuOpenIdsByPhone("15362469449");
        verify(client, never()).findOpenIdsByMobile("15362469449");
    }

    @Test
    void resolvesPhonesForMpowerUsingTestRecipientOrBusinessRecipients() {
        FeishuNotificationRecipientResolver testResolver =
                new FeishuNotificationRecipientResolver(mapper, client, "15362469449", "");

        assertThat(testResolver.resolveRecipientPhones(List.of(12L)))
                .containsExactly("15362469449");
        verify(mapper, never()).findActiveUserPhones(List.of(12L));

        FeishuNotificationRecipientResolver productionResolver =
                new FeishuNotificationRecipientResolver(mapper, client, "", "");
        when(mapper.findActiveUserPhones(List.of(12L))).thenReturn(List.of("+8615362469448"));

        assertThat(productionResolver.resolveRecipientPhones(List.of(12L, 12L, -1L)))
                .containsExactly("+8615362469448");
        verify(mapper).findActiveUserPhones(List.of(12L));
    }
}
