package com.adpulse.main.channel.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.adaccountasset.AdAccountAssetMapper;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetService;
import com.adpulse.main.adaccountasset.AdAccountAssetViews;
import com.adpulse.main.channel.dto.ChannelRequests.AccountBatch;
import com.adpulse.main.channel.dto.ChannelRequests.AccountImportItem;
import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.AvailableAccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelSave;
import com.adpulse.main.channel.dto.ChannelRequests.RateSave;
import com.adpulse.main.channel.dto.ChannelViews;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.AccountType;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import com.adpulse.main.channel.model.ChannelModels.Channel;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.time.LocalDate;
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

/** 渠道费率、批量账户和导入校验测试。 */
@ExtendWith(MockitoExtension.class)
class ChannelServiceTest {
    @Mock private ChannelMapper mapper;
    @Mock private AccountSnapshotProvider accountSnapshotProvider;
    @Mock private AccountQueryProvider accountQueryProvider;
    @Mock private AdAccountAssetMapper adAccountAssetMapper;
    @Mock private AdAccountAssetService adAccountAssetService;

    private ChannelService service;

    @BeforeEach
    void setUp() {
        service =
                new ChannelService(
                        mapper,
                        new ChannelExcelCodec(),
                        accountSnapshotProvider,
                        accountQueryProvider,
                        adAccountAssetMapper,
                        adAccountAssetService);
        org.mockito.Mockito.lenient()
                .when(accountSnapshotProvider.findByAccountIds(any()))
                .thenReturn(java.util.Map.of());
        CurrentUser user = new CurrentUser(9L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldRejectOverlappingRateRange() {
        Channel channel = new Channel();
        channel.setId(1L);
        channel.setChannelName("Meta渠道");
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.countRateOverlaps(1L, null, LocalDate.of(2026, 8, 1), null)).thenReturn(1);

        RateSave request =
                new RateSave(
                        new BigDecimal("3.5"), new BigDecimal("2"), LocalDate.of(2026, 8, 1), null);

        assertThatThrownBy(() -> service.createRate(1L, request))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessageContaining("重叠");
    }

    @Test
    void shouldBuildPaymentContextFromYesterdaySpendAndChannelAddress() {
        Channel channel = new Channel();
        channel.setId(1L);
        channel.setChannelName("Meta 渠道");
        channel.setPaymentAddress("收款地址快照");
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.sumChannelSpend(1L, LocalDate.now().minusDays(1)))
                .thenReturn(new BigDecimal("128.50"));

        var result = service.getPaymentContext(1L);

        assertThat(result.channelId()).isEqualTo("1");
        assertThat(result.channelYesterdayCost()).isEqualByComparingTo("128.50");
        assertThat(result.paymentAddress()).isEqualTo("收款地址快照");
    }

    @Test
    void shouldCreateAllBatchAccounts() {
        Channel channel = new Channel();
        channel.setId(1L);
        channel.setChannelName("Meta渠道");
        AccountType type = new AccountType();
        type.setId(2L);
        type.setAccountType("企业户");
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.findAccountTypeByName("企业户")).thenReturn(type);

        service.batchCreateAccounts(
                new AccountBatch(
                        1L,
                        List.of(
                                new AccountImportItem("123", "企业户"),
                                new AccountImportItem("456", "企业户"))));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(adAccountAssetService, org.mockito.Mockito.times(2))
                .upsertChannelAsset(captor.capture());
        assertThat(captor.getAllValues())
                .allMatch(
                        account ->
                                account.getAccountName().isEmpty()
                                        && account.getIsManuallyUpdated());
    }

    @Test
    void shouldEnrichAccountListFromSnapshotProvider() {
        Account account = new Account();
        account.setAccountId("123");
        account.setStatus(1);
        account.setConsumption(new BigDecimal("88.25"));
        when(accountQueryProvider.find(
                        any(),
                        org.mockito.ArgumentMatchers.eq(0),
                        org.mockito.ArgumentMatchers.eq(10)))
                .thenReturn(new AccountQueryProvider.PageResult(List.of(account), 1L));
        when(accountSnapshotProvider.findByAccountIds(List.of("123")))
                .thenReturn(
                        java.util.Map.of(
                                "123",
                                new AccountSnapshotProvider.AccountSnapshot(
                                        "123",
                                        "Mongo账户",
                                        2,
                                        null,
                                        8,
                                        "bm-1",
                                        new BigDecimal("10.50"),
                                        new BigDecimal("199.75"),
                                        null,
                                        null)));
        var result =
                service.listAccounts(
                        new AccountQuery(
                                1L,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                LocalDate.of(2026, 8, 1),
                                LocalDate.of(2026, 8, 24),
                                1,
                                10,
                                null));

        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.accountName()).isEqualTo("Mongo账户");
                            assertThat(item.status()).isEqualTo(2);
                            assertThat(item.synced()).isTrue();
                            assertThat(item.timezone()).isEqualTo(8);
                            assertThat(item.bmId()).isEqualTo("bm-1");
                            assertThat(item.balance()).isEqualByComparingTo("10.50");
                            assertThat(item.consumption()).isEqualByComparingTo("88.25");
                            assertThat(item.amountSpent()).isEqualByComparingTo("1.9975");
                        });
    }

    @Test
    void shouldMarkAccountAsUnsyncedWhenMongoSnapshotDoesNotExist() {
        Account account = new Account();
        account.setAccountId("missing");
        account.setStatus(1);
        when(accountQueryProvider.find(
                        any(),
                        org.mockito.ArgumentMatchers.eq(0),
                        org.mockito.ArgumentMatchers.eq(10)))
                .thenReturn(new AccountQueryProvider.PageResult(List.of(account), 1L));
        when(accountSnapshotProvider.findByAccountIds(List.of("missing")))
                .thenReturn(java.util.Map.of());

        var result =
                service.listAccounts(
                        new AccountQuery(
                                1L,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                null,
                                LocalDate.of(2026, 8, 1),
                                LocalDate.of(2026, 8, 24),
                                1,
                                10,
                                null));

        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.synced()).isFalse();
                            assertThat(item.status()).isEqualTo(1);
                        });
    }

    @Test
    void shouldListAccountsWithoutSpendDateRange() {
        AccountQuery query =
                new AccountQuery(
                        1L, null, null, null, null, null, null, null, null, null, null, null, null,
                        null, null, null, 1, 10, null);
        Account account = new Account();
        account.setAccountId("act_123");
        when(accountQueryProvider.find(query, 0, 10))
                .thenReturn(new AccountQueryProvider.PageResult(List.of(account), 1L));

        var result = service.listAccounts(query);

        assertThat(result.items())
                .singleElement()
                .extracting(ChannelViews.Account::accountId)
                .isEqualTo("act_123");
        assertThat(result.total()).isEqualTo(1L);
        verify(accountQueryProvider).find(query, 0, 10);
    }

    @Test
    void shouldQueryScopedAccountsThroughAccountQueryProvider() {
        AccountQuery query =
                new AccountQuery(
                        null, null, null, null, null, null, null, null, null, null, null, null,
                        null, null, null, null, 1, 10, null);
        Account account = new Account();
        account.setAccountId("act_456");
        when(accountQueryProvider.find(query, 0, 10))
                .thenReturn(new AccountQueryProvider.PageResult(List.of(account), 1L));

        var result = service.listAccounts(query);

        assertThat(result.total()).isEqualTo(1L);
        verify(accountQueryProvider).find(query, 0, 10);
    }

    @Test
    void shouldSummarizeAccountsWithoutSpendDateRange() {
        AccountQuery query =
                new AccountQuery(
                        1L, null, null, null, null, null, null, null, null, null, null, null, null,
                        null, null, null, 1, 10, null);

        var result = service.summarizeAccounts(query);

        assertThat(result.consumption()).isEqualByComparingTo(BigDecimal.ZERO);
        verify(accountQueryProvider).summarize(query);
    }

    @Test
    void shouldKeepDorisConsumptionInDollarsWhenSummarizingAccounts() {
        AccountQuery query =
                new AccountQuery(
                        1L,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        LocalDate.of(2026, 9, 23),
                        LocalDate.of(2026, 9, 23),
                        1,
                        10,
                        null);
        Aggregate aggregate = new Aggregate();
        aggregate.setConsumption(new BigDecimal("88.25"));
        aggregate.setAmountSpent(new BigDecimal("199.75"));
        when(accountQueryProvider.summarize(query)).thenReturn(aggregate);

        var result = service.summarizeAccounts(query);

        assertThat(result.consumption()).isEqualByComparingTo("88.25");
        assertThat(result.amountSpent()).isEqualByComparingTo("1.9975");
    }

    @Test
    void shouldRejectConsumptionFilterWithoutSpendDateRange() {
        AccountQuery query =
                new AccountQuery(
                        1L,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        BigDecimal.ZERO,
                        null,
                        null,
                        null,
                        null,
                        null,
                        1,
                        10,
                        null);

        assertThatThrownBy(() -> service.listAccounts(query))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessage("筛选消耗/花费区间时请选择完整时间");
    }

    @Test
    void shouldListAvailableAccountsWithoutSpendDateRange() {
        Channel channel = new Channel();
        channel.setId(1L);
        channel.setChannelName("Meta渠道");
        AvailableAccountQuery query =
                new AvailableAccountQuery(1L, null, null, 8, null, null, List.of("act_123"), 1, 10);
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.findAccountIdsByChannelId(1L)).thenReturn(List.of("act_123"));
        when(adAccountAssetService.listByAccountIds(List.of("act_123")))
                .thenReturn(List.of(assetView("act_123", "Meta渠道")));

        var result = service.listAvailableAccounts(query);

        assertThat(result.items())
                .singleElement()
                .extracting(ChannelViews.Account::accountId)
                .isEqualTo("act_123");
        assertThat(result.total()).isEqualTo(1L);
        verify(accountQueryProvider, never()).find(any(), any(Integer.class), any(Integer.class));
    }

    @Test
    void shouldUpdateAccountWhenItAlreadyBelongsToSameChannel() {
        Channel channel = new Channel();
        channel.setId(1L);
        channel.setChannelName("Meta渠道");
        AccountType type = new AccountType();
        type.setAccountType("企业户");
        AdAccountAsset existing = new AdAccountAsset();
        existing.setId(10L);
        existing.setChannelId(1L);
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.findAccountTypeByName("企业户")).thenReturn(type);
        when(adAccountAssetMapper.findByAccountId("123")).thenReturn(existing);

        service.batchCreateAccounts(
                new AccountBatch(1L, List.of(new AccountImportItem("act_123", "企业户"))));

        verify(adAccountAssetService).upsertChannelAsset(existing);
    }

    @Test
    void shouldReportExistingChannelNameWhenAccountBelongsToAnotherChannel() {
        Channel target = new Channel();
        target.setId(1L);
        target.setChannelName("新渠道");
        AccountType type = new AccountType();
        type.setAccountType("企业户");
        AdAccountAsset existing = new AdAccountAsset();
        existing.setId(10L);
        existing.setChannelId(2L);
        existing.setChannelName("旧渠道");
        when(mapper.findChannel(1L)).thenReturn(target);
        when(mapper.findAccountTypeByName("企业户")).thenReturn(type);
        when(adAccountAssetMapper.findByAccountId("123")).thenReturn(existing);

        assertThatThrownBy(
                        () ->
                                service.batchCreateAccounts(
                                        new AccountBatch(
                                                1L, List.of(new AccountImportItem("123", "企业户")))))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessage("账户[123]已归属其他渠道[旧渠道]");
    }

    @Test
    void shouldRejectNormalizedDuplicateAccountIds() {
        Channel channel = new Channel();
        channel.setId(1L);
        AccountType type = new AccountType();
        type.setAccountType("企业户");
        when(mapper.findChannel(1L)).thenReturn(channel);
        when(mapper.findAccountTypeByName("企业户")).thenReturn(type);

        assertThatThrownBy(
                        () ->
                                service.batchCreateAccounts(
                                        new AccountBatch(
                                                1L,
                                                List.of(
                                                        new AccountImportItem("123", "企业户"),
                                                        new AccountImportItem(
                                                                " act_123 ", "企业户")))))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessageContaining("重复的账户ID：123");
    }

    @Test
    void shouldReturnAllImportErrorsBeforeWriting() {
        byte[] template = new ChannelExcelCodec().template();
        when(mapper.findChannel(1L)).thenReturn(null);

        List<String> errors = service.importAccounts(template);

        assertThat(errors).hasSize(1).first().asString().contains("渠道不存在");
        verify(adAccountAssetService, never()).upsertChannelAsset(any());
    }

    @Test
    void shouldRejectIncompleteChannelCreation() {
        ChannelSave request =
                new ChannelSave(
                        "测试渠道",
                        null,
                        null,
                        1,
                        "Mpower",
                        1,
                        "预付",
                        "USD",
                        BigDecimal.ZERO,
                        BigDecimal.ZERO,
                        "address",
                        "https://example.com",
                        null,
                        null,
                        null);

        assertThatThrownBy(() -> service.createChannel(request))
                .isInstanceOf(ChannelService.ChannelException.class)
                .hasMessageContaining("必填信息");
    }

    @Test
    void shouldDefaultMissingChannelAmountsToZero() {
        Channel[] insertedChannel = new Channel[1];
        doAnswer(
                        invocation -> {
                            Channel channel = invocation.getArgument(0);
                            channel.setId(1L);
                            insertedChannel[0] = channel;
                            return 1;
                        })
                .when(mapper)
                .insertChannel(any(Channel.class));
        when(mapper.findChannel(1L)).thenAnswer(invocation -> insertedChannel[0]);
        ChannelSave request =
                new ChannelSave(
                        "测试渠道",
                        "测试",
                        "TEST01",
                        1,
                        "Mpower",
                        1,
                        "预付实消",
                        "USD",
                        null,
                        null,
                        "address",
                        "https://example.com",
                        null,
                        null,
                        null);

        service.createChannel(request);

        assertThat(insertedChannel[0].getBuyoutAmount()).isEqualByComparingTo(BigDecimal.ZERO);
        assertThat(insertedChannel[0].getRechargeAmount()).isEqualByComparingTo(BigDecimal.ZERO);
    }

    private AdAccountAssetViews.Account assetView(String accountId, String channelName) {
        return new AdAccountAssetViews.Account(
                accountId,
                "测试账户",
                1,
                null,
                "AVAILABLE",
                "企业户",
                "",
                "",
                "",
                "",
                "",
                "",
                "8",
                "",
                "",
                "",
                "",
                "",
                null,
                "1",
                channelName,
                false,
                "SYNCED",
                null,
                List.of());
    }
}
