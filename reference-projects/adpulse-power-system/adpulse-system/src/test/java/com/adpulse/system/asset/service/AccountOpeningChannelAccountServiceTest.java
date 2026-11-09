package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 广告户申请办理时渠道账户分配的并发安全校验测试。 */
@ExtendWith(MockitoExtension.class)
class AccountOpeningChannelAccountServiceTest {
    @Mock private DynamicAssetFlowMapper flowMapper;

    private AccountOpeningChannelAccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountOpeningChannelAccountService(flowMapper);
    }

    @Test
    void shouldAssignSelectedAccountsToApplicantWhenAssignedToOtherUsers() {
        when(flowMapper.lockActiveChannelAccounts(List.of("act_1", "act_2")))
                .thenReturn(
                        List.of(
                                Map.of("accountId", "account_1", "channelName", "渠道一"),
                                Map.of("accountId", "account_2", "channelName", "渠道二")));
        when(flowMapper.findAssignedChannelAccountIds(List.of("account_1", "account_2"), 12L))
                .thenReturn(List.of());
        when(flowMapper.insertChannelAccountAssignments(
                        List.of("account_1", "account_2"), 101L, 12L, "申请人", 7L))
                .thenReturn(2);
        when(flowMapper.assignChannelAccounts(List.of("account_1", "account_2"), 12L, "申请人", 7L))
                .thenReturn(2);

        var result = service.assignSelectedAccounts("act_1;act_2;act_1", 101L, 12L, "申请人", 7L);

        assertThat(result)
                .extracting(AccountOpeningChannelAccountService.SelectedAccount::channelName)
                .containsExactly("渠道一", "渠道二");
        verify(flowMapper)
                .insertChannelAccountAssignments(
                        List.of("account_1", "account_2"), 101L, 12L, "申请人", 7L);
        verify(flowMapper).assignChannelAccounts(List.of("account_1", "account_2"), 12L, "申请人", 7L);
    }

    @Test
    void shouldRejectAccountsAlreadyAssignedToApplicantAndListAccountIds() {
        when(flowMapper.lockActiveChannelAccounts(List.of("account_1", "account_2")))
                .thenReturn(
                        List.of(
                                Map.of("accountId", "account_1", "channelName", "渠道一"),
                                Map.of("accountId", "account_2", "channelName", "渠道二")));
        when(flowMapper.findAssignedChannelAccountIds(List.of("account_1", "account_2"), 12L))
                .thenReturn(List.of("account_2"));

        assertThatThrownBy(
                        () ->
                                service.assignSelectedAccounts(
                                        "account_1;account_2", 101L, 12L, "申请人", 7L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("以下广告账户已分配给申请人，请勿重复分配：account_2");
        verify(flowMapper, never())
                .insertChannelAccountAssignments(
                        List.of("account_1", "account_2"), 101L, 12L, "申请人", 7L);
        verify(flowMapper, never())
                .assignChannelAccounts(List.of("account_1", "account_2"), 12L, "申请人", 7L);
    }

    @Test
    void shouldRejectWhenSelectedAccountDoesNotExist() {
        when(flowMapper.lockActiveChannelAccounts(List.of("act_1"))).thenReturn(List.of());

        assertThatThrownBy(() -> service.assignSelectedAccounts("act_1", 101L, 12L, "申请人", 7L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("所选广告账户不存在，请刷新后重试");
    }
}
