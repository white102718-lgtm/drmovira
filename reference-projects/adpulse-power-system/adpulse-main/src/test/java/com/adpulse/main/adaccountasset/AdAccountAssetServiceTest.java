package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.ActiveUser;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetAssignment;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.UserDepartment;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentReplace;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.BatchUpdate;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.BatchUpdateField;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.ImportItem;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.PageFilter;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.Save;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.List;
import java.util.Set;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 广告账户统一台账、平台快照与使用人规则测试。 */
@ExtendWith(MockitoExtension.class)
class AdAccountAssetServiceTest {
    @Mock private MongoTemplate mongoTemplate;
    @Mock private AdAccountAssetMapper assetMapper;
    @Mock private AdAccountAssetAssignmentMapper assignmentMapper;
    @Mock private AccountAttributeMapper accountAttributeMapper;
    @Mock private AdAccountUserMapper userMapper;
    @Mock private ChannelMapper channelMapper;

    private AdAccountAssetService service;

    @BeforeEach
    void setUp() {
        service =
                new AdAccountAssetService(
                        mongoTemplate,
                        assetMapper,
                        assignmentMapper,
                        accountAttributeMapper,
                        userMapper,
                        channelMapper,
                        "fb_ad_accounts");
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, "", user.authorities()));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldPageTheAssetLedgerWithoutLoadingTheWholeTable() {
        AdAccountAsset asset = asset("200", "资产表账户");
        when(assetMapper.countPage(null, PageFilter.EMPTY)).thenReturn(21L);
        when(assetMapper.findPage(null, PageFilter.EMPTY, 10L, 10)).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var page = service.list(null, PageFilter.EMPTY, 2, 10);

        assertThat(page.items()).extracting(item -> item.accountId()).containsExactly("200");
        assertThat(page.items().get(0).syncStatus()).isEqualTo("PLATFORM_MISSING");
        assertThat(page.items().get(0).accountDailyLimit()).isNull();
        assertThat(page.total()).isEqualTo(21L);
        assertThat(page.page()).isEqualTo(2);
        assertThat(page.pageSize()).isEqualTo(10);
    }

    @Test
    void shouldLookupRequestedAccountUnionWithoutLoadingTheWholeLedger() {
        AdAccountAsset asset = asset("200", "资产表账户");
        when(assetMapper.findByAccountIds(List.of("100", "200"))).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of(new Document("_id", "100").append("name", "平台账户")));

        var accounts = service.listByAccountIds(List.of(" act_100 ", "200", "act_100"));

        assertThat(accounts).extracting(item -> item.accountId()).containsExactly("200", "100");
        verify(assetMapper, never()).findAll();
        verify(mongoTemplate, never()).findAll(Document.class, "fb_ad_accounts");
        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate).find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_accounts"));
        assertThat(queryCaptor.getValue().getQueryObject().toJson()).contains("100", "200");
    }

    @Test
    void shouldNormalizeAndForwardPageFilters() {
        PageFilter rawFilter =
                new PageFilter(
                        List.of(" 平台账户 ", "备用账户"),
                        List.of(" 200 "),
                        List.of(1, 2, 1),
                        List.of(" 企业户 ", "个人户"),
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        List.of(" assigned ", "available"),
                        List.of(" 测试用户 "),
                        List.of(" 投放一组 "),
                        List.of(" 库存用户 "));
        when(assetMapper.countPage(eq("BM"), any(PageFilter.class))).thenReturn(0L);
        when(assetMapper.findPage(eq("BM"), any(PageFilter.class), eq(0L), eq(20)))
                .thenReturn(List.of());

        service.list(" BM ", rawFilter, 1, 20);

        ArgumentCaptor<PageFilter> filterCaptor = ArgumentCaptor.forClass(PageFilter.class);
        verify(assetMapper).countPage(eq("BM"), filterCaptor.capture());
        assertThat(filterCaptor.getValue().accountNames()).containsExactly("平台账户", "备用账户");
        assertThat(filterCaptor.getValue().accountIds()).containsExactly("200");
        assertThat(filterCaptor.getValue().accountStatuses()).containsExactly(1, 2);
        assertThat(filterCaptor.getValue().accountTypes()).containsExactly("企业户", "个人户");
        assertThat(filterCaptor.getValue().inventoryStatuses())
                .containsExactly("ASSIGNED", "AVAILABLE");
        assertThat(filterCaptor.getValue().usageUsers()).containsExactly("测试用户");
        assertThat(filterCaptor.getValue().usageDepartments()).containsExactly("投放一组");
        assertThat(filterCaptor.getValue().inventoryAssigneeNames()).containsExactly("库存用户");
    }

    @Test
    void shouldLoadAllFilteredAccountsWithoutPaging() {
        PageFilter rawFilter =
                new PageFilter(
                        List.of(" 品牌账户 "),
                        null,
                        List.of(1, 2),
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
                        List.of(" available "),
                        null,
                        null,
                        null);
        AdAccountAsset asset = asset("200", "品牌账户");
        when(assetMapper.findAllByFilter(eq("BM"), any(PageFilter.class)))
                .thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var accounts = service.listAll(" BM ", rawFilter);

        assertThat(accounts).extracting(item -> item.accountId()).containsExactly("200");
        ArgumentCaptor<PageFilter> filterCaptor = ArgumentCaptor.forClass(PageFilter.class);
        verify(assetMapper).findAllByFilter(eq("BM"), filterCaptor.capture());
        assertThat(filterCaptor.getValue().accountNames()).containsExactly("品牌账户");
        assertThat(filterCaptor.getValue().accountStatuses()).containsExactly(1, 2);
        assertThat(filterCaptor.getValue().inventoryStatuses()).containsExactly("AVAILABLE");
        verify(assetMapper, never()).countPage(any(), any());
        verify(assetMapper, never()).findPage(any(), any(), anyLong(), anyInt());
    }

    @Test
    void shouldAlwaysUseMongoNameStatusAndDailyLimit() {
        AdAccountAsset asset = asset("100", "旧名称");
        asset.setAccountStatus(2);
        when(assetMapper.countPage(null, PageFilter.EMPTY)).thenReturn(1L);
        when(assetMapper.findPage(null, PageFilter.EMPTY, 0L, 20)).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(
                        List.of(
                                new Document("_id", "100")
                                        .append("name", "平台名称")
                                        .append("account_status", 1)
                                        .append(
                                                "account_dsl",
                                                new Decimal128(new BigDecimal("123.45")))));

        var account = service.list(null, PageFilter.EMPTY, 1, 20).items().getFirst();

        assertThat(account.accountName()).isEqualTo("平台名称");
        assertThat(account.accountStatus()).isEqualTo(1);
        assertThat(account.accountDailyLimit()).isEqualByComparingTo("123.45");
    }

    @Test
    void shouldUseAssetNameWhenMongoNameIsBlank() {
        AdAccountAsset asset = asset("100", "导入名称");
        when(assetMapper.countPage(null, PageFilter.EMPTY)).thenReturn(1L);
        when(assetMapper.findPage(null, PageFilter.EMPTY, 0L, 20)).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of(new Document("_id", "100").append("name", " ")));

        var account = service.list(null, PageFilter.EMPTY, 1, 20).items().getFirst();

        assertThat(account.accountName()).isEqualTo("导入名称");
    }

    @Test
    void shouldExposeDeliveryDateFromAssetLedger() {
        AdAccountAsset asset = asset("100", "资产账户");
        asset.setDeliveryDate(LocalDate.of(2026, 9, 11));
        when(assetMapper.countPage(null, PageFilter.EMPTY)).thenReturn(1L);
        when(assetMapper.findPage(null, PageFilter.EMPTY, 0L, 20)).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var account = service.list(null, PageFilter.EMPTY, 1, 20).items().getFirst();

        assertThat(account.deliveryDate()).isEqualTo(LocalDate.of(2026, 9, 11));
    }

    @Test
    void shouldExposeAssetAndAssignmentDatesForMyAccounts() {
        AdAccountAsset asset = asset("100", "资产账户");
        asset.setCreatedAt(LocalDateTime.of(2026, 9, 15, 12, 7, 11));
        AdAccountAssetAssignment assignment = new AdAccountAssetAssignment();
        assignment.setId(91L);
        assignment.setAdAccountAssetId(asset.getId());
        assignment.setUserId(7L);
        assignment.setUserName("测试用户");
        assignment.setIsPrimary(true);
        assignment.setAssignmentStatus("ACTIVE");
        assignment.setAssignmentSource("APPLICATION");
        assignment.setApplicationId(88L);
        assignment.setAssignedAt(LocalDateTime.of(2026, 9, 15, 12, 7, 12));
        when(assignmentMapper.findActiveAssetIdsByUserId(7L)).thenReturn(List.of(asset.getId()));
        when(assetMapper.findByIds(List.of(asset.getId()))).thenReturn(List.of(asset));
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId())))
                .thenReturn(List.of(assignment));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var account = service.listMine().getFirst();

        assertThat(account.createdAt()).isEqualTo(asset.getCreatedAt());
        assertThat(account.assignments().getFirst().applicationId()).isEqualTo("88");
        assertThat(account.assignments().getFirst().assignedAt())
                .isEqualTo(assignment.getAssignedAt());
        verify(mongoTemplate, never()).findAll(Document.class, "fb_ad_accounts");
    }

    @Test
    void shouldIncludeStatusTwoBanEventsInLifecycle() {
        AdAccountAsset asset = asset("100", "测试账户");
        asset.setCreatedAt(LocalDateTime.of(2026, 9, 16, 8, 0));
        when(assetMapper.findByAccountId("100")).thenReturn(asset);
        when(assetMapper.findByAccountIds(List.of("100"))).thenReturn(List.of(asset));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());
        when(assignmentMapper.findActiveByAssetIds(List.of(asset.getId()))).thenReturn(List.of());
        when(assignmentMapper.findHistoryByAssetId(asset.getId())).thenReturn(List.of());
        Date detectedAt =
                Date.from(
                        LocalDateTime.of(2026, 9, 17, 9, 30)
                                .atZone(ZoneId.of("Asia/Shanghai"))
                                .toInstant());
        when(mongoTemplate.find(
                        any(Query.class), eq(Document.class), eq("fb_ad_account_ban_events")))
                .thenReturn(
                        List.of(
                                new Document("_id", "ban-1")
                                        .append("account_id", "100")
                                        .append("previous_status", 1)
                                        .append("current_status", 2)
                                        .append("disable_reason", 3)
                                        .append("detected_at", detectedAt)
                                        .append("source", "fb_business_sync")));

        var detail = service.lifecycle("act_100");

        assertThat(detail.events())
                .anySatisfy(
                        event -> {
                            assertThat(event.id()).isEqualTo("facebook-ban-ban-1");
                            assertThat(event.eventType()).isEqualTo("FACEBOOK_ACCOUNT_BANNED");
                            assertThat(event.status()).isEqualTo("DISABLED");
                            assertThat(event.description()).isEqualTo("Facebook 广告账户状态变为封户");
                            assertThat(event.extraData()).contains("\"disableReason\": 3");
                            assertThat(event.occurredAt())
                                    .isEqualTo(LocalDateTime.of(2026, 9, 17, 9, 30));
                        });
        ArgumentCaptor<Query> queryCaptor = ArgumentCaptor.forClass(Query.class);
        verify(mongoTemplate)
                .find(queryCaptor.capture(), eq(Document.class), eq("fb_ad_account_ban_events"));
        assertThat(queryCaptor.getValue().getQueryObject().toJson())
                .contains("account_id", "current_status", "detected_at");
        verify(assetMapper, never()).findAll();
        verify(mongoTemplate, never()).findAll(Document.class, "fb_ad_accounts");
    }

    @Test
    void shouldIgnoreClientNameWhenSavingExistingAccount() {
        AdAccountAsset existing = asset("100", "平台名称");
        existing.setDeliveryDate(LocalDate.of(2026, 9, 11));
        when(assetMapper.findByAccountId("100")).thenReturn(existing);
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(
                        new Document("_id", "100")
                                .append("name", "平台名称")
                                .append("account_status", 1));
        when(assetMapper.findByAccountIds(List.of("100"))).thenReturn(List.of(existing));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(
                        List.of(
                                new Document("_id", "100")
                                        .append("name", "平台名称")
                                        .append("account_status", 1)));
        when(assignmentMapper.findActiveByAssetIds(List.of(existing.getId())))
                .thenReturn(List.of());

        service.update(
                "100",
                new Save(
                        "客户端名称", "企业户", null, null, null, null, null, null, null, null, null,
                        "重点账户"));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountName()).isEqualTo("平台名称");
        assertThat(captor.getValue().getDeliveryDate()).isEqualTo(LocalDate.of(2026, 9, 11));
        assertThat(captor.getValue().getIsManuallyUpdated()).isTrue();
        assertThat(captor.getValue().getRemark()).isEqualTo("重点账户");
    }

    @Test
    void shouldCreateMissingAssetWithBlankPlatformName() {
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);

        service.update(
                "300",
                new Save(
                        "导入名称", "企业户", null, null, null, null, null, null, null, null, null, null));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountName()).isEmpty();
    }

    @Test
    void shouldMapRemarkFromImportItemToSaveRequest() {
        ImportItem item =
                new ImportItem(
                        2, "100", "账户", "企业户", null, null, null, null, null, null, null, null, null,
                        null, "导入备注", null);

        assertThat(item.toSave().remark()).isEqualTo("导入备注");
    }

    @Test
    void shouldCreateMissingAssetWhenImportingAccount() {
        ImportItem item =
                new ImportItem(
                        2, "300", "导入名称", "企业户", null, null, null, null, null, null, null, null,
                        null, null, "导入备注", null);
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);
        AdAccountAsset persisted = asset("300", "导入名称");
        when(assetMapper.findByAccountId("300")).thenReturn(null, null, persisted, persisted);
        when(assetMapper.findByAccountIds(List.of("300"))).thenReturn(List.of(persisted));
        when(assignmentMapper.findActiveByAssetIds(List.of(persisted.getId())))
                .thenReturn(List.of());

        var result = service.importAccounts(List.of(item));

        assertThat(result.successCount()).isEqualTo(1);
        assertThat(result.failures()).isEmpty();
        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountId()).isEqualTo("300");
        assertThat(captor.getValue().getAccountName()).isEqualTo("导入名称");
        assertThat(captor.getValue().getRemark()).isEqualTo("导入备注");
    }

    @Test
    void shouldReplaceImportedUsageUsersAndDeriveAssignedStatus() {
        AdAccountAsset existing = asset("100", "账户");
        AdAccountAssetAssignment previous = assignment(existing, 1L, 8L, "旧使用人", "旧部门");
        when(userMapper.findAllActiveUsers())
                .thenReturn(List.of(activeUser(9L, "张三"), activeUser(10L, "李四")));
        when(assetMapper.findByAccountId("100")).thenReturn(existing);
        when(assetMapper.findByAccountIds(List.of("100"))).thenReturn(List.of(existing));
        when(assignmentMapper.findActiveByAssetIds(List.of(existing.getId())))
                .thenReturn(List.of(previous));
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var result = service.importAccounts(List.of(importItem("100", "张三、李四，张三")));

        assertThat(result.successCount()).isEqualTo(1);
        assertThat(result.failures()).isEmpty();
        verify(assignmentMapper).release(eq(existing.getId()), eq(8L), eq(7L), any(Long.class));
        verify(assignmentMapper, org.mockito.Mockito.times(2))
                .upsert(any(AdAccountAssetAssignment.class));
        verify(assetMapper).updateInventoryStatus(existing.getId(), "ASSIGNED", 7L);
        verify(userMapper, never()).findDisplayName(any());
        verify(userMapper, never()).findCurrentDepartmentName(any());
    }

    @Test
    void shouldClearImportedUsageUsersAndDeriveAvailableStatus() {
        AdAccountAsset existing = asset("100", "账户");
        AdAccountAssetAssignment previous = assignment(existing, 1L, 8L, "旧使用人", "旧部门");
        when(assetMapper.findByAccountId("100")).thenReturn(existing);
        when(assetMapper.findByAccountIds(List.of("100"))).thenReturn(List.of(existing));
        when(assignmentMapper.findActiveByAssetIds(List.of(existing.getId())))
                .thenReturn(List.of(previous));
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var result = service.importAccounts(List.of(importItem("100", " ")));

        assertThat(result.successCount()).isEqualTo(1);
        verify(assignmentMapper).release(eq(existing.getId()), eq(8L), eq(7L), any(Long.class));
        verify(assetMapper).updateInventoryStatus(existing.getId(), "AVAILABLE", 7L);
    }

    @Test
    void shouldRejectAmbiguousImportedUsageUserBeforeUpdatingAccount() {
        when(userMapper.findAllActiveUsers())
                .thenReturn(List.of(activeUser(9L, "同名用户"), activeUser(10L, "同名用户")));

        var result = service.importAccounts(List.of(importItem("100", "同名用户")));

        assertThat(result.successCount()).isZero();
        assertThat(result.failures())
                .singleElement()
                .satisfies(
                        failure -> assertThat(failure.message()).isEqualTo("使用人姓名重复，无法唯一匹配：同名用户"));
        verify(assetMapper, never()).upsert(any());
    }

    @Test
    void shouldRejectMissingImportedUsageUserBeforeUpdatingAccount() {
        var result = service.importAccounts(List.of(importItem("100", "已停用用户")));

        assertThat(result.successCount()).isZero();
        assertThat(result.failures())
                .singleElement()
                .satisfies(failure -> assertThat(failure.message()).isEqualTo("使用人不存在或已停用：已停用用户"));
        verify(assetMapper, never()).upsert(any());
    }

    @Test
    void shouldPreferPlatformNameWhenImportingAccount() {
        ImportItem item =
                new ImportItem(
                        2, "300", "导入名称", "企业户", null, null, null, null, null, null, null, null,
                        null, null, null, null);
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(new Document("_id", "300").append("name", "平台名称"));

        service.importAccounts(List.of(item));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountName()).isEqualTo("平台名称");
    }

    @Test
    void shouldUseImportedNameWhenPlatformNameIsBlank() {
        ImportItem item =
                new ImportItem(
                        2, "300", "导入名称", "企业户", null, null, null, null, null, null, null, null,
                        null, null, null, null);
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(new Document("_id", "300").append("name", " "));

        service.importAccounts(List.of(item));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountName()).isEqualTo("导入名称");
    }

    @Test
    void shouldKeepExistingNameWhenImportedNameIsBlank() {
        AdAccountAsset existing = asset("300", "已有名称");
        ImportItem item =
                new ImportItem(
                        2, "300", " ", "企业户", null, null, null, null, null, null, null, null, null,
                        null, null, null);
        when(assetMapper.findByAccountId("300")).thenReturn(existing);
        when(mongoTemplate.findOne(any(), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(null);

        service.importAccounts(List.of(item));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper).upsert(captor.capture());
        assertThat(captor.getValue().getAccountName()).isEqualTo("已有名称");
    }

    @Test
    void shouldRejectOverlongImportRemarkAsRowFailure() {
        ImportItem item =
                new ImportItem(
                        2,
                        "100",
                        "账户",
                        "企业户",
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
                        "备".repeat(501),
                        null);

        var result = service.importAccounts(List.of(item));

        assertThat(result.successCount()).isZero();
        assertThat(result.failures())
                .singleElement()
                .satisfies(
                        failure -> {
                            assertThat(failure.line()).isEqualTo(2);
                            assertThat(failure.message()).isEqualTo("备注不能超过 500 字");
                        });
    }

    @Test
    void shouldSetInventoryStatusWhenReplacingAssignments() {
        AdAccountAsset existing = asset("100", "平台账户");
        when(assetMapper.findByAccountId("100")).thenReturn(existing);
        when(assetMapper.findByAccountIds(List.of("100"))).thenReturn(List.of(existing));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());
        when(assignmentMapper.findActiveByAssetIds(List.of(existing.getId())))
                .thenReturn(List.of());
        when(userMapper.findDisplayName(9L)).thenReturn("使用人");
        when(userMapper.findCurrentDepartmentName(9L)).thenReturn("投放一组");

        service.replaceAssignments("100", new AssignmentReplace(List.of(9L), "MANUAL", "ASSIGNED"));

        ArgumentCaptor<AdAccountAssetModels.AdAccountAssetAssignment> assignmentCaptor =
                ArgumentCaptor.forClass(AdAccountAssetModels.AdAccountAssetAssignment.class);
        verify(assignmentMapper).upsert(assignmentCaptor.capture());
        assertThat(assignmentCaptor.getValue().getUsageTeamName()).isEqualTo("投放一组");
        verify(assetMapper).updateInventoryStatus(existing.getId(), "ASSIGNED", 7L);
    }

    @Test
    void shouldResolveCurrentDepartmentsForEveryUsageUser() {
        AdAccountAsset existing = asset("100", "平台账户");
        existing.setRemark("列表备注");
        AdAccountAssetAssignment firstAssignment = assignment(existing, 1L, 9L, "使用人一", "旧部门一");
        AdAccountAssetAssignment secondAssignment = assignment(existing, 2L, 10L, "使用人二", "旧部门二");
        when(assetMapper.countPage(null, PageFilter.EMPTY)).thenReturn(1L);
        when(assetMapper.findPage(null, PageFilter.EMPTY, 0L, 20)).thenReturn(List.of(existing));
        when(assignmentMapper.findActiveByAssetIds(List.of(existing.getId())))
                .thenReturn(List.of(firstAssignment, secondAssignment));
        when(userMapper.findCurrentDepartments(List.of(9L, 10L)))
                .thenReturn(List.of(userDepartment(9L, "技术部"), userDepartment(10L, "设计部")));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());

        var account = service.list(null, PageFilter.EMPTY, 1, 20).items().getFirst();

        assertThat(account.usageDepartmentName()).isEqualTo("技术部、设计部");
        assertThat(account.remark()).isEqualTo("列表备注");
    }

    @Test
    void shouldUpdateOnlySelectedFieldsAndAllowClearingOptionalValuesInBatch() {
        AdAccountAsset first = asset("100", "账户一");
        first.setAccountType("企业户");
        first.setManagedBm("旧 BM");
        first.setTimezone("Asia/Shanghai");
        AdAccountAsset second = asset("200", "账户二");
        second.setAccountType("个人户");
        second.setManagedBm("另一个旧 BM");
        second.setTimezone("UTC");
        when(assetMapper.findByAccountIds(List.of("100", "200")))
                .thenReturn(List.of(first, second));
        when(mongoTemplate.find(any(Query.class), eq(Document.class), eq("fb_ad_accounts")))
                .thenReturn(List.of());
        when(assignmentMapper.findActiveByAssetIds(List.of(first.getId(), second.getId())))
                .thenReturn(List.of());

        service.batchUpdate(
                new BatchUpdate(
                        List.of("act_100", "200"),
                        Set.of(
                                BatchUpdateField.MANAGED_BM,
                                BatchUpdateField.TIMEZONE,
                                BatchUpdateField.REMARK),
                        null,
                        null,
                        null,
                        "新的 BM",
                        null,
                        null,
                        null,
                        "",
                        null,
                        null,
                        "",
                        null,
                        null));

        ArgumentCaptor<AdAccountAsset> captor = ArgumentCaptor.forClass(AdAccountAsset.class);
        verify(assetMapper, org.mockito.Mockito.times(2)).upsert(captor.capture());
        assertThat(captor.getAllValues())
                .allSatisfy(
                        asset -> {
                            assertThat(asset.getManagedBm()).isEqualTo("新的 BM");
                            assertThat(asset.getTimezone()).isNull();
                            assertThat(asset.getRemark()).isNull();
                            assertThat(asset.getAccountType()).isIn("企业户", "个人户");
                            assertThat(asset.getIsManuallyUpdated()).isTrue();
                        });
        verify(mongoTemplate, never()).findAll(Document.class, "fb_ad_accounts");
    }

    private AdAccountAsset asset(String accountId, String accountName) {
        AdAccountAsset asset = new AdAccountAsset();
        asset.setId(Long.valueOf(accountId));
        asset.setAccountId(accountId);
        asset.setAccountName(accountName);
        asset.setUpdatedAt(java.time.LocalDateTime.of(2026, 1, 1, 0, 0));
        return asset;
    }

    private ActiveUser activeUser(long userId, String displayName) {
        ActiveUser user = new ActiveUser();
        user.setUserId(userId);
        user.setDisplayName(displayName);
        return user;
    }

    private ImportItem importItem(String accountId, String usageUsers) {
        return new ImportItem(
                2,
                accountId,
                "账户",
                "企业户",
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
                usageUsers);
    }

    private AdAccountAssetAssignment assignment(
            AdAccountAsset asset,
            long assignmentId,
            long userId,
            String userName,
            String usageTeamName) {
        AdAccountAssetAssignment assignment = new AdAccountAssetAssignment();
        assignment.setId(assignmentId);
        assignment.setAdAccountAssetId(asset.getId());
        assignment.setUserId(userId);
        assignment.setUserName(userName);
        assignment.setUsageTeamName(usageTeamName);
        assignment.setIsPrimary(true);
        assignment.setAssignmentStatus("ACTIVE");
        assignment.setAssignmentSource("APPLICATION");
        return assignment;
    }

    private UserDepartment userDepartment(long userId, String departmentName) {
        UserDepartment department = new UserDepartment();
        department.setUserId(userId);
        department.setDepartmentName(departmentName);
        return department;
    }
}
