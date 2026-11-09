package com.adpulse.main.channel.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 非 Doris 渠道账户查询范围测试。 */
@ExtendWith(MockitoExtension.class)
class AssetAccountQueryProviderTest {
    @Mock private ChannelMapper mapper;

    @Test
    void shouldPageAccountsFromAssetLedger() {
        AssetAccountQueryProvider provider = new AssetAccountQueryProvider(mapper);
        Account account = new Account();
        account.setAccountId("123");
        when(mapper.findAssetAccounts(query(), 0, 20)).thenReturn(List.of(account));
        when(mapper.countAssetAccounts(query())).thenReturn(1L);

        var page = provider.find(query(), 0, 20);

        assertThat(page.total()).isEqualTo(1L);
        assertThat(page.items()).singleElement().extracting(Account::getAccountId).isEqualTo("123");
    }

    @Test
    void shouldSummarizeAccountsFromAssetLedger() {
        AssetAccountQueryProvider provider = new AssetAccountQueryProvider(mapper);
        Aggregate aggregate = new Aggregate();
        when(mapper.summarizeAssetAccounts(query())).thenReturn(aggregate);

        var summary = provider.summarize(query());

        assertThat(summary).isSameAs(aggregate);
        verify(mapper).summarizeAssetAccounts(query());
    }

    private AccountQuery query() {
        return new AccountQuery(
                null, null, null, null, null, null, null, null, null, null, null, null, null, null,
                null, null, 1, 20, null, null);
    }
}
