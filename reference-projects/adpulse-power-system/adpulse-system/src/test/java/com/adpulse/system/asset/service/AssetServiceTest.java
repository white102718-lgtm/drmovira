package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.dto.AssetImportViews;
import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.AssetImportLog;
import com.adpulse.system.asset.model.MediaAsset;
import com.adpulse.system.auth.service.MfaSecretCipher;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 资产与审批配置业务规则测试。 */
@ExtendWith(MockitoExtension.class)
class AssetServiceTest {

    @Mock private AssetMapper mapper;
    @Mock private AssetExcelCodec excelCodec;
    @Mock private MfaSecretCipher secretCipher;

    private AssetService service;

    @BeforeEach
    void setUp() {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        service = new AssetService(mapper, excelCodec, secretCipher);
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldSoftDeleteApprovalConfigWithCurrentOperator() {
        when(mapper.softDeleteConfig(eq(31L), anyLong(), eq(7L))).thenReturn(1);

        service.deleteApprovalConfig(31L);

        verify(mapper).softDeleteConfig(eq(31L), anyLong(), eq(7L));
    }

    @Test
    void shouldRejectDeletingMissingApprovalConfig() {
        when(mapper.softDeleteConfig(eq(31L), anyLong(), eq(7L))).thenReturn(0);

        assertThatThrownBy(() -> service.deleteApprovalConfig(31L))
                .isInstanceOf(BusinessException.class)
                .hasMessage("审批配置不存在");
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "AD_ACCOUNT",
                "PERSONAL",
                "BM",
                "PIXEL",
                "TG",
                "PAGE",
                "COMPUTER",
                "MOBILE",
                "STATIC_IP",
                "EMAIL"
            })
    void shouldSupportAllInventoryAssetTypes(String assetType) {
        when(mapper.findAssets(assetType, null, null)).thenReturn(List.of());

        service.assets(assetType, null);

        verify(mapper).findAssets(assetType, null, null);
    }

    @Test
    void shouldRegisterOpenedAccountsAsAssignedAdvertisingAssets() {
        List<MediaAsset> registered =
                service.registerOpenedAdAccounts(
                        "79001;79002;79001", "测试广告户", "9900108", "测试渠道", 88L, 12L, "申请人", 7L);

        assertThat(registered).hasSize(2);
        verify(mapper, org.mockito.Mockito.times(2))
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "AD_ACCOUNT".equals(asset.getAssetType())
                                                && "ASSIGNED".equals(asset.getStatus())
                                                && Long.valueOf(88L)
                                                        .equals(asset.getApplicationId())
                                                && Long.valueOf(12L).equals(asset.getAssigneeId())
                                                && "9900108".equals(asset.getChannelId())));
    }

    @Test
    void shouldReuseExistingAdvertisingAssetForAnotherApplicant() {
        MediaAsset existingAsset = new MediaAsset();
        existingAsset.setId(901L);
        existingAsset.setAssetCode("79001");
        when(mapper.insertAsset(any())).thenThrow(new DuplicateKeyException("already exists"));
        when(mapper.findAssetByTypeAndCode("AD_ACCOUNT", "79001")).thenReturn(existingAsset);

        List<MediaAsset> registered =
                service.registerOpenedAdAccounts(
                        "79001", "测试广告户", "9900108", "测试渠道", 99L, 13L, "另一申请人", 7L);

        assertThat(registered).containsExactly(existingAsset);
        verify(mapper).findAssetByTypeAndCode("AD_ACCOUNT", "79001");
    }

    @Test
    void shouldResolveSocialApplicationToInventoryTypeAndSubtype() {
        AssetService.InventorySelection wechatSelection =
                service.resolveInventorySelection(
                        "TG",
                        Map.of("socialAssetType", "微信号"),
                        Map.of("assetTypeFieldKey", "socialAssetType"));
        AssetService.InventorySelection facebookSelection =
                service.resolveInventorySelection(
                        "TG",
                        Map.of("socialAssetType", "Facebook 账号"),
                        Map.of("assetTypeFieldKey", "socialAssetType"));

        assertThat(wechatSelection.assetType()).isEqualTo("PERSONAL");
        assertThat(wechatSelection.subtype()).isEqualTo("wechat");
        assertThat(facebookSelection.assetType()).isEqualTo("PERSONAL");
        assertThat(facebookSelection.subtype()).isEqualTo("fb");
    }

    @Test
    void shouldMatchEncryptedPersonalInventorySubtype() {
        when(secretCipher.decrypt("encrypted")).thenReturn("{\"inventorySubtype\":\"wechat\"}");
        when(secretCipher.decrypt("encrypted-fb")).thenReturn("{\"inventorySubtype\":\"fb\"}");
        when(secretCipher.decrypt("encrypted-personal"))
                .thenReturn("{\"inventorySubtype\":\"personal\"}");

        assertThat(service.matchesInventorySubtype("encrypted", "wechat")).isTrue();
        assertThat(service.matchesInventorySubtype("encrypted", "fb")).isFalse();
        assertThat(service.matchesInventorySubtype("encrypted-fb", "fb")).isTrue();
        assertThat(service.matchesInventorySubtype("encrypted-personal", "fb")).isFalse();
        assertThat(service.matchesInventorySubtype(null, "fb")).isTrue();
    }

    @Test
    void shouldListPersonalAssetWithoutSubtypeUnderFbInventory() {
        MediaAsset asset = new MediaAsset();
        asset.setId(3L);
        asset.setAssetType("PERSONAL");
        asset.setAssetName("E2E验收Facebook-001");
        asset.setAssetCode("e2e-personal-20260821@example.test");
        asset.setAssigneeId(7L);
        asset.setStatus("ASSIGNED");
        when(mapper.findAssets("PERSONAL", 7L, null)).thenReturn(List.of(asset));

        var page =
                service.searchAssets(
                        new AssetRequests.AssetSearch(
                                "PERSONAL", "fb", null, Map.of(), Map.of(), Map.of(), 1, 20, true));

        assertThat(page.items()).containsExactly(asset);
        assertThat(page.total()).isEqualTo(1);
    }

    @Test
    void shouldMatchAnyCandidateInsideEachAssetFilter() {
        MediaAsset asset = new MediaAsset();
        asset.setId(9L);
        asset.setAssetName("Alpha 资产");
        asset.setAssetType("PIXEL");
        asset.setStatus("ASSIGNED");
        asset.setUsageTeam("固化团队");
        asset.setUsageDepartmentNames("投放一组、投放三组");
        asset.setAssigneeDepartmentName("主使用人部门");
        when(mapper.findAssets(null, null, null)).thenReturn(List.of(asset));

        var page =
                service.searchAssets(
                        new AssetRequests.AssetSearch(
                                null,
                                null,
                                null,
                                Map.of(),
                                Map.of(
                                        "name",
                                        List.of("不存在", "alpha"),
                                        "status",
                                        List.of("available", "allocated"),
                                        "usageDepartment",
                                        List.of("投放二组", "投放一组")),
                                Map.of(
                                        "name", "text",
                                        "status", "select",
                                        "usageDepartment", "text"),
                                1,
                                20,
                                false));

        assertThat(page.items()).containsExactly(asset);
        assertThat(page.total()).isEqualTo(1);
    }

    @Test
    void shouldReturnAllMatchingAssetsWithoutPaginationForExport() {
        MediaAsset first = new MediaAsset();
        first.setId(10L);
        first.setAssetType("PIXEL");
        first.setAssetName("品牌像素一");
        MediaAsset second = new MediaAsset();
        second.setId(11L);
        second.setAssetType("PIXEL");
        second.setAssetName("品牌像素二");
        when(mapper.findAssets("PIXEL", null, null)).thenReturn(List.of(first, second));
        var request =
                new AssetRequests.AssetSearch(
                        "PIXEL", null, "品牌", Map.of(), Map.of(), Map.of(), 1, 1, false);

        var page = service.searchAssets(request);
        var all = service.searchAllAssets(request);

        assertThat(page.items()).containsExactly(first);
        assertThat(page.total()).isEqualTo(2);
        assertThat(all).containsExactly(first, second);
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "AD_ACCOUNT",
                "PERSONAL",
                "BM",
                "PIXEL",
                "TG",
                "PAGE",
                "COMPUTER",
                "MOBILE",
                "STATIC_IP",
                "EMAIL"
            })
    void shouldCreateAssetWithoutChannel(String assetType) {
        service.createAsset(
                new AssetRequests.AssetSave(
                        assetType,
                        "E2E测试资产",
                        "E2E-001",
                        null,
                        null,
                        null,
                        null,
                        null,
                        "测试库存",
                        "AVAILABLE",
                        null,
                        null,
                        null));

        verify(mapper).insertAsset(any());
    }

    @Test
    void shouldCreateWechatAssetWithoutChannel() {
        when(secretCipher.encrypt("{\"inventorySubtype\":\"wechat\"}")).thenReturn("encrypted");

        service.createAsset(
                new AssetRequests.AssetSave(
                        "PERSONAL",
                        "E2E测试微信",
                        "wechat-e2e-001",
                        null,
                        null,
                        null,
                        null,
                        "{\"inventorySubtype\":\"wechat\"}",
                        "测试库存",
                        "AVAILABLE",
                        null,
                        null,
                        null));

        verify(mapper).insertAsset(any());
    }

    @Test
    void shouldCreateAssignedAssetWithCanonicalActiveUserName() {
        when(mapper.findActiveUserName(12L)).thenReturn("张三");

        service.createAsset(
                new AssetRequests.AssetSave(
                        "COMPUTER",
                        "设计电脑",
                        "PC-001",
                        null,
                        null,
                        null,
                        null,
                        null,
                        "测试库存",
                        "ASSIGNED",
                        12L,
                        null,
                        null));

        verify(mapper)
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "ASSIGNED".equals(asset.getStatus())
                                                && Long.valueOf(12L).equals(asset.getAssigneeId())
                                                && "张三".equals(asset.getAssigneeName())));
    }

    @Test
    void shouldDerivePixelAllocationFromItsProjectWithoutUsageUsers() {
        when(mapper.countActiveProject("1001", "项目 A")).thenReturn(1);
        when(mapper.findActiveDepartmentName(10L)).thenReturn("投放一组");
        doAnswer(
                        invocation -> {
                            invocation.getArgument(0, MediaAsset.class).setId(101L);
                            return 1;
                        })
                .when(mapper)
                .insertAsset(any());

        service.createAsset(
                new AssetRequests.AssetSave(
                        "PIXEL",
                        "购买像素",
                        "PX-001",
                        "1001",
                        "项目 A",
                        null,
                        null,
                        null,
                        "测试库存",
                        "AVAILABLE",
                        null,
                        null,
                        10L));

        verify(mapper)
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "ASSIGNED".equals(asset.getStatus())
                                                && "1001".equals(asset.getProjectId())
                                                && "投放一组".equals(asset.getUsageTeam())
                                                && asset.getAssigneeId() == null));
        verify(mapper, org.mockito.Mockito.never())
                .deactivatePixelUsageUsers(anyLong(), anyLong(), anyLong());
    }

    @Test
    void shouldReleaseAllPixelsAssignedToCompletedProject() {
        MediaAsset pixel = new MediaAsset();
        pixel.setId(100L);
        pixel.setStatus("ASSIGNED");
        pixel.setProjectName("项目 A");
        pixel.setUsageTeam("投放一组");
        AssetLifecycleService lifecycleService =
                org.mockito.Mockito.mock(AssetLifecycleService.class);
        AssetService lifecycleAwareService =
                new AssetService(mapper, excelCodec, secretCipher, lifecycleService);
        when(mapper.findAssignedPixelsByProject("1001")).thenReturn(List.of(pixel));
        when(mapper.deactivatePixelUsageAssignmentsForProject(eq("1001"), anyLong(), eq(7L)))
                .thenReturn(2);
        when(mapper.releasePixelsForProject(eq("1001"), eq(7L))).thenReturn(2);

        int released = lifecycleAwareService.releasePixelsForProject("1001", 7L);

        assertThat(released).isEqualTo(2);
        verify(mapper).deactivatePixelUsageAssignmentsForProject(eq("1001"), anyLong(), eq(7L));
        verify(mapper).releasePixelsForProject("1001", 7L);
        verify(lifecycleService).record("RELEASED", pixel, "项目结项释放像素");
    }

    @Test
    void shouldAssignAdvertisingAccountToAllSelectedUsageUsers() {
        when(mapper.findActiveUserName(12L)).thenReturn("张三");
        when(mapper.findActiveUserName(13L)).thenReturn("李四");
        doAnswer(
                        invocation -> {
                            invocation.getArgument(0, MediaAsset.class).setId(102L);
                            return 1;
                        })
                .when(mapper)
                .insertAsset(any());

        service.createAsset(
                new AssetRequests.AssetSave(
                        "AD_ACCOUNT",
                        "广告账户",
                        "ACT-001",
                        null,
                        null,
                        null,
                        null,
                        null,
                        "测试库存",
                        "ASSIGNED",
                        null,
                        List.of(12L, 13L),
                        null));

        verify(mapper).deactivatePixelUsageUsers(eq(102L), anyLong(), eq(7L));
        verify(mapper, times(2)).upsertPixelUsageUser(eq(102L), anyLong(), any(), eq(7L));
    }

    @Test
    void shouldAssignImportedAssetWhenExcelContainsUsageUser() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        List.of("*资产编号", "电脑名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "*资产编号", "PC-001",
                                "电脑名称", "设计电脑",
                                "使用人", "李四",
                                "备注", "导入测试"));
        when(excelCodec.read(any(), eq("computer"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(mapper.findActiveUserIdsByName("李四")).thenReturn(List.of(12L));
        when(mapper.findActiveUserName(12L)).thenReturn("李四");
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        var result = service.importAssets(new byte[] {1}, "computer");

        assertThat(result.successCount()).isEqualTo(1);
        verify(mapper)
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "ASSIGNED".equals(asset.getStatus())
                                                && Long.valueOf(12L).equals(asset.getAssigneeId())
                                                && "李四".equals(asset.getAssigneeName())));
    }

    @Test
    void shouldUpdateImportedAssetWhenIdentifierAlreadyExists() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        List.of("*资产编号", "电脑名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "*资产编号", "PC-001",
                                "电脑名称", "更新后的电脑",
                                "使用人", "",
                                "备注", "更新备注"));
        MediaAsset existing = new MediaAsset();
        existing.setId(101L);
        existing.setAssetType("COMPUTER");
        existing.setAssetCode("PC-001");
        existing.setStatus("ASSIGNED");
        existing.setApplicationId(88L);
        when(excelCodec.read(any(), eq("computer"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(mapper.findAssetByTypeAndCode("COMPUTER", "PC-001")).thenReturn(existing);
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        var result = service.importAssets(new byte[] {1}, "computer");

        assertThat(result.successCount()).isEqualTo(1);
        verify(mapper, never()).insertAsset(any());
        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "更新后的电脑".equals(asset.getAssetName())
                                                && "AVAILABLE".equals(asset.getStatus())
                                                && asset.getApplicationId() == null
                                                && "更新备注".equals(asset.getRemark())));
    }

    @Test
    void shouldRejectLaterDuplicateIdentifierInSameImportFile() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        List.of("*资产编号", "电脑名称", "备注"));
        AssetExcelCodec.ParsedRow first =
                new AssetExcelCodec.ParsedRow(2, Map.of("*资产编号", "PC-001", "电脑名称", "第一台电脑"));
        AssetExcelCodec.ParsedRow duplicate =
                new AssetExcelCodec.ParsedRow(3, Map.of("*资产编号", "PC-001", "电脑名称", "第二台电脑"));
        when(excelCodec.read(any(), eq("computer"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(first, duplicate)));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");
        when(excelCodec.writeFailures(any(), any())).thenReturn(new byte[] {1});

        var result = service.importAssets(new byte[] {1}, "computer");

        assertThat(result.successCount()).isEqualTo(1);
        assertThat(result.failures())
                .containsExactly(new AssetImportViews.Failure(3, "同一文件中存在重复的资产唯一标识"));
        verify(mapper, times(1)).insertAsset(any());
    }

    @Test
    void shouldPersistImportLogForCurrentOperator() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        List.of("*资产编号", "电脑名称", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(2, Map.of("*资产编号", "PC-IMPORT-001", "电脑名称", "导入电脑"));
        when(excelCodec.read(any(), eq("computer"), eq("C:\\uploads\\资产导入.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        service.importAssets(new byte[] {1}, "computer", "C:\\uploads\\资产导入.xlsx");

        verify(mapper)
                .insertImportLog(
                        org.mockito.ArgumentMatchers.argThat(
                                importLog ->
                                        Long.valueOf(7L).equals(importLog.getOperatorId())
                                                && "computer".equals(importLog.getAssetSubtype())
                                                && "资产导入.xlsx".equals(importLog.getFileName())
                                                && importLog.getTotalCount() == 1
                                                && importLog.getSuccessCount() == 1
                                                && importLog.getFailureCount() == 0));
    }

    @Test
    void shouldOnlyReadImportHistoryForCurrentOperator() {
        AssetImportLog importLog = new AssetImportLog();
        importLog.setId(88L);
        importLog.setAssetSubtype("tg");
        importLog.setFileName("TG导入.xlsx");
        importLog.setTotalCount(2);
        importLog.setSuccessCount(1);
        importLog.setFailureCount(1);
        importLog.setFailureDetails("[{\"line\":3,\"message\":\"资产标识已存在\"}]");
        importLog.setCreatedAt(LocalDateTime.of(2026, 9, 7, 10, 30));
        when(mapper.findImportLogsByOperatorId(7L, 20, 20)).thenReturn(List.of(importLog));
        when(mapper.countImportLogsByOperatorId(7L)).thenReturn(41L);

        PageResult<AssetImportViews.History> history = service.importHistory(2, 20);

        assertThat(history.items())
                .singleElement()
                .satisfies(
                        record -> {
                            assertThat(record.id()).isEqualTo(88L);
                            assertThat(record.failures())
                                    .containsExactly(new AssetImportViews.Failure(3, "资产标识已存在"));
                        });
        assertThat(history.total()).isEqualTo(41);
        assertThat(history.page()).isEqualTo(2);
        assertThat(history.pageSize()).isEqualTo(20);
        verify(mapper).findImportLogsByOperatorId(7L, 20, 20);
        verify(mapper).countImportLogsByOperatorId(7L);
    }

    @Test
    void shouldClampImportHistoryPagination() {
        when(mapper.findImportLogsByOperatorId(7L, 0, 100)).thenReturn(List.of());
        when(mapper.countImportLogsByOperatorId(7L)).thenReturn(0L);

        PageResult<AssetImportViews.History> history = service.importHistory(0, 200);

        assertThat(history.page()).isEqualTo(1);
        assertThat(history.pageSize()).isEqualTo(100);
        verify(mapper).findImportLogsByOperatorId(7L, 0, 100);
    }

    @Test
    void shouldOnlyDownloadFailedImportFileForCurrentOperator() {
        AssetImportLog importLog = new AssetImportLog();
        importLog.setFileName("TG导入.xlsx");
        importLog.setFailedFileCiphertext("encrypted-file");
        when(mapper.findImportLogByIdAndOperatorId(88L, 7L)).thenReturn(importLog);
        when(secretCipher.decrypt("encrypted-file")).thenReturn("failed-file-base64");

        AssetImportViews.FailedFile failedFile = service.failedImportFile(88L);

        assertThat(failedFile.contentBase64()).isEqualTo("failed-file-base64");
        assertThat(failedFile.fileName()).isEqualTo("TG导入失败数据.xlsx");
        verify(mapper).findImportLogByIdAndOperatorId(88L, 7L);
    }

    @Test
    void shouldUseRequiredPageNameAsAssetCodeWhenPageIdIsBlank() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "page",
                        "PAGE",
                        "主页",
                        "主页 ID",
                        "*主页名称",
                        Set.of("*主页名称"),
                        List.of("主页 ID", "*主页名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "主页 ID", "",
                                "*主页名称", "测试主页",
                                "使用人", "",
                                "备注", "导入测试"));
        when(excelCodec.read(any(), eq("page"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        var result = service.importAssets(new byte[] {1}, "page");

        assertThat(result.successCount()).isEqualTo(1);
        verify(mapper)
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "测试主页".equals(asset.getAssetCode())
                                                && "测试主页".equals(asset.getAssetName())
                                                && asset.getChannelId() == null
                                                && asset.getChannelName() == null
                                                && asset.getProjectId() == null
                                                && asset.getProjectName() == null));
    }

    @ParameterizedTest
    @ValueSource(strings = {"未分配", "未设置", "—"})
    void shouldTreatLegacyUsageUserPlaceholdersAsEmpty(String usageUser) {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "computer",
                        "COMPUTER",
                        "电脑",
                        "*资产编号",
                        "电脑名称",
                        Set.of("*资产编号"),
                        List.of("*资产编号", "电脑名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "*资产编号", "PC-LEGACY-001",
                                "电脑名称", "历史电脑",
                                "使用人", usageUser,
                                "备注", ""));
        when(excelCodec.read(any(), eq("computer"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        var result = service.importAssets(new byte[] {1}, "computer");

        assertThat(result.successCount()).isEqualTo(1);
        verify(mapper)
                .insertAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "AVAILABLE".equals(asset.getStatus())
                                                && asset.getAssigneeId() == null
                                                && asset.getAssigneeName() == null));
        verify(mapper, never()).findActiveUserIdsByName(any());
    }

    @Test
    void shouldUpdateLegacyPageByNameAndUseNameAsNewIdentifier() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "page",
                        "PAGE",
                        "主页",
                        "主页 ID",
                        "*主页名称",
                        Set.of("*主页名称"),
                        List.of("主页 ID", "*主页名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "主页 ID", "PAGE-NEW-ID",
                                "*主页名称", "品牌主页",
                                "使用人", "",
                                "备注", "最新资料"));
        MediaAsset legacyPage = new MediaAsset();
        legacyPage.setId(102L);
        legacyPage.setAssetType("PAGE");
        legacyPage.setAssetCode("PAGE-OLD-ID");
        legacyPage.setStatus("AVAILABLE");
        when(excelCodec.read(any(), eq("page"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(mapper.findAssetByTypeAndCode("PAGE", "品牌主页")).thenReturn(null);
        when(mapper.findAssetsByTypeAndName("PAGE", "品牌主页")).thenReturn(List.of(legacyPage));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        var result = service.importAssets(new byte[] {1}, "page");

        assertThat(result.successCount()).isEqualTo(1);
        verify(mapper, never()).insertAsset(any());
        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                asset ->
                                        "品牌主页".equals(asset.getAssetCode())
                                                && "品牌主页".equals(asset.getAssetName())));
    }

    @Test
    void shouldRejectImportedPageWhenRequiredPageNameIsMissing() {
        AssetExcelCodec.ImportSpec spec =
                new AssetExcelCodec.ImportSpec(
                        "page",
                        "PAGE",
                        "主页",
                        "主页 ID",
                        "*主页名称",
                        Set.of("*主页名称"),
                        List.of("主页 ID", "*主页名称", "使用人", "备注"));
        AssetExcelCodec.ParsedRow row =
                new AssetExcelCodec.ParsedRow(2, Map.of("主页 ID", "PAGE-001"));
        when(excelCodec.read(any(), eq("page"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(spec, List.of(row)));
        when(excelCodec.writeFailures(any(), any())).thenReturn(new byte[] {1});

        var result = service.importAssets(new byte[] {1}, "page");

        assertThat(result.successCount()).isZero();
        assertThat(result.failures())
                .extracting(failure -> failure.message())
                .containsExactly("主页名称不能为空");
    }

    @Test
    void shouldNormalizeImportedSelectLabelsToStoredValues() {
        AssetExcelCodec.ImportSpec fbSpec =
                new AssetExcelCodec.ImportSpec(
                        "fb",
                        "PERSONAL",
                        "个号",
                        "*邮箱",
                        "名字",
                        Set.of("*个号创建日期", "*邮箱", "*密码", "*2fa"),
                        List.of("*个号创建日期", "名字", "*邮箱", "*密码", "*2fa", "性别", "备注"));
        AssetExcelCodec.ParsedRow fbRow =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "*个号创建日期", "2026-09-03",
                                "名字", "测试账号",
                                "*邮箱", "test@example.com",
                                "*密码", "password",
                                "*2fa", "secret",
                                "性别", "男",
                                "备注", "导入测试"));
        AssetExcelCodec.ImportSpec bmSpec =
                new AssetExcelCodec.ImportSpec(
                        "bm",
                        "BM",
                        "BM",
                        "*BMID",
                        "BM 名称",
                        Set.of("*BMID"),
                        List.of("BM 名称", "*BMID", "是否移除供应商", "备注"));
        AssetExcelCodec.ParsedRow bmRow =
                new AssetExcelCodec.ParsedRow(
                        2,
                        Map.of(
                                "BM 名称", "测试 BM",
                                "*BMID", "BM-001",
                                "是否移除供应商", "否",
                                "备注", "导入测试"));
        when(excelCodec.read(any(), eq("fb"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(fbSpec, List.of(fbRow)));
        when(excelCodec.read(any(), eq("bm"), eq("未命名导入文件.xlsx")))
                .thenReturn(new AssetExcelCodec.ParsedWorkbook(bmSpec, List.of(bmRow)));
        when(secretCipher.encrypt(any())).thenReturn("encrypted");

        assertThat(service.importAssets(new byte[] {1}, "fb").successCount()).isEqualTo(1);
        assertThat(service.importAssets(new byte[] {1}, "bm").successCount()).isEqualTo(1);

        ArgumentCaptor<String> detailsCaptor = ArgumentCaptor.forClass(String.class);
        verify(secretCipher, times(2)).encrypt(detailsCaptor.capture());
        assertThat(detailsCaptor.getAllValues())
                .anySatisfy(details -> assertThat(details).contains("\"gender\":\"MALE\""))
                .anySatisfy(details -> assertThat(details).contains("\"supplierRemoved\":\"NO\""));
    }

    @ParameterizedTest
    @CsvSource({
        "AD_ACCOUNT,ad_account,accountId",
        "PERSONAL,fb,email",
        "BM,bm,bmId",
        "PIXEL,pixel,pixelId",
        "TG,telegram,phoneNumber",
        "PAGE,page,pageName",
        "COMPUTER,computer,assetCode",
        "MOBILE,mobile,deviceCode",
        "STATIC_IP,static_ip,ipAddress",
        "EMAIL,email,email"
    })
    void shouldSaveEditsForEverySupportedAssetType(
            String assetType, String subtype, String identifierKey) {
        String assetCode = "EDIT-" + assetType;
        String details =
                String.format(
                        "{\"inventorySubtype\":\"%s\",\"%s\":\"%s\"}",
                        subtype, identifierKey, assetCode);
        MediaAsset existing = new MediaAsset();
        existing.setId(101L);
        existing.setAssetType(assetType);
        existing.setAssetCode(assetCode);
        existing.setSecretData("encrypted-current-details");
        existing.setStatus("AVAILABLE");
        when(mapper.findAsset(101L)).thenReturn(existing);
        when(secretCipher.decrypt("encrypted-current-details")).thenReturn(details);
        when(secretCipher.encrypt(any())).thenReturn("encrypted-details");

        service.updateAsset(
                101L,
                new AssetRequests.AssetSave(
                        assetType,
                        "编辑保存-" + assetType,
                        assetCode,
                        null,
                        null,
                        null,
                        null,
                        details,
                        "编辑保存回归测试",
                        "AVAILABLE",
                        null,
                        null,
                        null));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                saved ->
                                        assetType.equals(saved.getAssetType())
                                                && ("编辑保存-" + assetType)
                                                        .equals(saved.getAssetName())
                                                && assetCode.equals(saved.getAssetCode())
                                                && "AVAILABLE".equals(saved.getStatus())
                                                && "编辑保存回归测试".equals(saved.getRemark())));
    }

    @Test
    void shouldRejectChangingAssetTypeDuringManualEdit() {
        MediaAsset asset = editableComputerAsset();
        when(mapper.findAsset(21L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-computer"))
                .thenReturn("{\"inventorySubtype\":\"computer\",\"assetCode\":\"PC-001\"}");

        assertThatThrownBy(
                        () ->
                                service.updateAsset(
                                        21L,
                                        assetSave(
                                                "MOBILE",
                                                "PC-001",
                                                "{\"inventorySubtype\":\"mobile\",\"deviceCode\":\"PC-001\"}")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("资产类型创建后不可修改");

        verify(mapper, never()).updateAsset(any());
        verify(secretCipher, never()).encrypt(any());
    }

    @Test
    void shouldRejectChangingPersonalAssetSubtypeDuringManualEdit() {
        MediaAsset asset = new MediaAsset();
        asset.setId(21L);
        asset.setAssetType("PERSONAL");
        asset.setAssetCode("person@example.com");
        asset.setSecretData("encrypted-personal");
        asset.setStatus("AVAILABLE");
        when(mapper.findAsset(21L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-personal"))
                .thenReturn("{\"inventorySubtype\":\"fb\",\"email\":\"person@example.com\"}");

        assertThatThrownBy(
                        () ->
                                service.updateAsset(
                                        21L,
                                        assetSave(
                                                "PERSONAL",
                                                "person@example.com",
                                                "{\"inventorySubtype\":\"wechat\",\"wechatId\":\"person@example.com\"}")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("资产子类型创建后不可修改");

        verify(mapper, never()).updateAsset(any());
        verify(secretCipher, never()).encrypt(any());
    }

    @Test
    void shouldRejectChangingAssetIdentifierDuringManualEdit() {
        MediaAsset asset = editableComputerAsset();
        when(mapper.findAsset(21L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-computer"))
                .thenReturn("{\"inventorySubtype\":\"computer\",\"assetCode\":\"PC-001\"}");

        assertThatThrownBy(
                        () ->
                                service.updateAsset(
                                        21L,
                                        assetSave(
                                                "COMPUTER",
                                                "PC-002",
                                                "{\"inventorySubtype\":\"computer\",\"assetCode\":\"PC-002\"}")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("资产唯一标识创建后不可修改");

        verify(mapper, never()).updateAsset(any());
        verify(secretCipher, never()).encrypt(any());
    }

    @Test
    void shouldRejectAssignedAssetWithoutActiveUser() {
        assertThatThrownBy(
                        () ->
                                service.createAsset(
                                        new AssetRequests.AssetSave(
                                                "COMPUTER",
                                                "设计电脑",
                                                "PC-001",
                                                null,
                                                null,
                                                null,
                                                null,
                                                null,
                                                "测试库存",
                                                "ASSIGNED",
                                                12L,
                                                null,
                                                null)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("请选择有效使用人");
    }

    @Test
    void shouldAllowEditingAssignedAssetAndClearUserWhenAvailable() {
        MediaAsset asset = editableComputerAsset();
        asset.setStatus("ASSIGNED");
        asset.setAssigneeId(12L);
        asset.setAssigneeName("张三");
        when(mapper.findAsset(21L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-computer"))
                .thenReturn("{\"inventorySubtype\":\"computer\",\"assetCode\":\"PC-001\"}");
        when(secretCipher.encrypt(any())).thenReturn("updated-computer");

        service.updateAsset(
                21L,
                new AssetRequests.AssetSave(
                        "COMPUTER",
                        "设计电脑",
                        "PC-001",
                        null,
                        null,
                        "{\"inventorySubtype\":\"computer\",\"assetCode\":\"PC-001\"}",
                        null,
                        null,
                        "测试库存",
                        "AVAILABLE",
                        null,
                        null,
                        null));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                value ->
                                        "AVAILABLE".equals(value.getStatus())
                                                && value.getAssigneeId() == null
                                                && value.getAssigneeName() == null));
    }

    private MediaAsset editableComputerAsset() {
        MediaAsset asset = new MediaAsset();
        asset.setId(21L);
        asset.setAssetType("COMPUTER");
        asset.setAssetCode("PC-001");
        asset.setSecretData("encrypted-computer");
        asset.setStatus("AVAILABLE");
        return asset;
    }

    private AssetRequests.AssetSave assetSave(
            String assetType, String assetCode, String secretData) {
        return new AssetRequests.AssetSave(
                assetType,
                "编辑后的资产名称",
                assetCode,
                null,
                null,
                null,
                null,
                secretData,
                "编辑后的备注",
                "AVAILABLE",
                null,
                null,
                null);
    }

    @Test
    void shouldBatchUpdateSelectedDetailsAndClearOptionalValues() {
        MediaAsset asset = new MediaAsset();
        asset.setId(81L);
        asset.setAssetType("BM");
        asset.setAssetCode("100200300");
        asset.setAssetName("旧 BM 名称");
        asset.setSecretData("encrypted-details");
        asset.setStatus("AVAILABLE");
        when(mapper.findAsset(81L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-details"))
                .thenReturn(
                        "{\"inventorySubtype\":\"bm\",\"bmId\":\"100200300\",\"bmName\":\"旧 BM 名称\",\"usagePurpose\":\"投放\"}");
        when(secretCipher.encrypt(any())).thenReturn("updated-details");

        service.batchUpdateAssets(
                new AssetRequests.AssetBatchUpdate(
                        List.of(81L),
                        Set.of(AssetRequests.AssetBatchField.REMARK),
                        Map.of("bmName", ""),
                        null,
                        null,
                        "",
                        null,
                        null,
                        null,
                        null,
                        null,
                        null));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                value ->
                                        "100200300".equals(value.getAssetCode())
                                                && "100200300".equals(value.getAssetName())
                                                && value.getRemark() == null
                                                && "updated-details"
                                                        .equals(value.getSecretData())));
        verify(secretCipher)
                .encrypt(
                        org.mockito.ArgumentMatchers.argThat(
                                details ->
                                        details.contains("\"bmName\":\"\"")
                                                && details.contains("\"usagePurpose\":\"投放\"")));
    }

    @Test
    void shouldReturnSpreadsheetUpdateWithoutDecryptingTheSameAssetTwice() {
        MediaAsset asset = new MediaAsset();
        asset.setId(50L);
        asset.setAssetType("BM");
        asset.setAssetCode("123123123");
        asset.setAssetName("123123123");
        asset.setSecretData("encrypted-details");
        asset.setStatus("ASSIGNED");
        when(mapper.findAsset(50L)).thenReturn(asset);
        when(secretCipher.decrypt(any()))
                .thenAnswer(
                        invocation -> {
                            String value = invocation.getArgument(0);
                            if ("encrypted-details".equals(value)) {
                                return "{\"inventorySubtype\":\"bm\",\"bmId\":\"123123123\",\"usagePurpose\":\"你猜\"}";
                            }
                            if ("updated-details".equals(value)) {
                                return "{\"inventorySubtype\":\"bm\",\"bmId\":\"123123123\",\"usagePurpose\":\"你猜1\"}";
                            }
                            throw new IllegalStateException("资产明细被重复解密");
                        });
        when(secretCipher.encrypt(any())).thenReturn("updated-details");
        AssetRequests.AssetSave values =
                new AssetRequests.AssetSave(
                        "BM",
                        "123123123",
                        "123123123",
                        null,
                        null,
                        "9900108",
                        "测试渠道",
                        null,
                        "我不猜",
                        "ASSIGNED",
                        1L,
                        List.of(1L),
                        null);

        var result =
                service.spreadsheetSave(
                        new AssetRequests.AssetSpreadsheetSave(
                                "bm",
                                List.of(
                                        new AssetRequests.AssetSpreadsheetRow(
                                                50L,
                                                values,
                                                Set.of(),
                                                Map.of("usagePurpose", "你猜1"),
                                                List.of(1L),
                                                null))));

        assertThat(result.createdCount()).isZero();
        assertThat(result.updatedCount()).isEqualTo(1);
        assertThat(result.items())
                .singleElement()
                .satisfies(
                        updated ->
                                assertThat(updated.getSecretData())
                                        .contains("\"usagePurpose\":\"你猜1\""));
        verify(secretCipher, times(3)).decrypt(any());
    }

    @Test
    void shouldBatchQueryAssetsByNormalizedIdentifiers() {
        MediaAsset asset = new MediaAsset();
        asset.setId(50L);
        asset.setAssetType("BM");
        asset.setAssetCode("123123123");
        when(mapper.findAssetsByTypeAndCodes("BM", List.of("123123123")))
                .thenReturn(List.of(asset));

        var result =
                service.batchQueryAssetsByIdentifiers(
                        new AssetRequests.AssetIdentifierBatchQuery(
                                "BM", List.of(" 123123123 ", "123123123")));

        assertThat(result).containsExactly(asset);
        verify(mapper).findAssetsByTypeAndCodes("BM", List.of("123123123"));
    }

    @Test
    void shouldUpdateExistingAssetWhenSpreadsheetNewRowIdentifierAlreadyExists() {
        MediaAsset asset = new MediaAsset();
        asset.setId(50L);
        asset.setAssetType("BM");
        asset.setAssetCode("123123123");
        asset.setAssetName("123123123");
        asset.setSecretData("encrypted-details");
        asset.setStatus("ASSIGNED");
        when(mapper.findAssetByTypeAndCode("BM", "123123123")).thenReturn(asset);
        when(mapper.findAsset(50L)).thenReturn(asset);
        when(secretCipher.decrypt("encrypted-details"))
                .thenReturn(
                        "{\"inventorySubtype\":\"bm\",\"bmId\":\"123123123\",\"usagePurpose\":\"旧用途\"}");
        when(secretCipher.encrypt(any())).thenReturn("updated-details");
        AssetRequests.AssetSave values =
                new AssetRequests.AssetSave(
                        "BM",
                        "123123123",
                        "123123123",
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        "ASSIGNED",
                        null,
                        null,
                        null);

        var result =
                service.spreadsheetSave(
                        new AssetRequests.AssetSpreadsheetSave(
                                "bm",
                                List.of(
                                        new AssetRequests.AssetSpreadsheetRow(
                                                null,
                                                values,
                                                Set.of(),
                                                Map.of("usagePurpose", "新用途"),
                                                null,
                                                null))));

        assertThat(result.createdCount()).isZero();
        assertThat(result.updatedCount()).isEqualTo(1);
        verify(mapper, never()).insertAsset(any());
        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                updated ->
                                        "123123123".equals(updated.getAssetCode())
                                                && Long.valueOf(50L).equals(updated.getId())));
        verify(secretCipher)
                .encrypt(
                        org.mockito.ArgumentMatchers.argThat(
                                details -> details.contains("\"usagePurpose\":\"新用途\"")));
    }

    @Test
    void shouldBatchAssignPixelsToProjectAndSynchronizeInventoryStatus() {
        MediaAsset asset = new MediaAsset();
        asset.setId(82L);
        asset.setAssetType("PIXEL");
        asset.setAssetCode("pixel-001");
        asset.setAssetName("测试像素");
        asset.setStatus("AVAILABLE");
        asset.setUsageTeam("原团队");
        when(mapper.findAsset(82L)).thenReturn(asset);
        when(mapper.countActiveProject("1001", "项目 A")).thenReturn(1);

        service.batchUpdateAssets(
                new AssetRequests.AssetBatchUpdate(
                        List.of(82L),
                        Set.of(AssetRequests.AssetBatchField.PROJECT),
                        Map.of(),
                        null,
                        null,
                        "1001",
                        "项目 A",
                        null,
                        null,
                        null,
                        null,
                        null));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                value ->
                                        "1001".equals(value.getProjectId())
                                                && "项目 A".equals(value.getProjectName())
                                                && "原团队".equals(value.getUsageTeam())
                                                && "ASSIGNED".equals(value.getStatus())
                                                && value.getAssigneeId() == null));
    }

    @Test
    void shouldBatchClearPixelProjectTeamAndRestoreAvailableStatus() {
        MediaAsset asset = new MediaAsset();
        asset.setId(84L);
        asset.setAssetType("PIXEL");
        asset.setAssetCode("pixel-003");
        asset.setAssetName("测试像素 3");
        asset.setProjectId("1001");
        asset.setProjectName("项目 A");
        asset.setUsageTeam("投放一组");
        asset.setStatus("ASSIGNED");
        when(mapper.findAsset(84L)).thenReturn(asset);

        service.batchUpdateAssets(
                new AssetRequests.AssetBatchUpdate(
                        List.of(84L),
                        Set.of(AssetRequests.AssetBatchField.PROJECT),
                        Map.of(),
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                value ->
                                        value.getProjectId() == null
                                                && value.getProjectName() == null
                                                && value.getUsageTeam() == null
                                                && "AVAILABLE".equals(value.getStatus())
                                                && value.getAssigneeId() == null));
    }

    @Test
    void shouldBatchChangePixelUsageTeamWithoutChangingProject() {
        MediaAsset asset = new MediaAsset();
        asset.setId(83L);
        asset.setAssetType("PIXEL");
        asset.setAssetCode("pixel-002");
        asset.setAssetName("测试像素 2");
        asset.setProjectId("1001");
        asset.setProjectName("项目 A");
        asset.setStatus("ASSIGNED");
        when(mapper.findAsset(83L)).thenReturn(asset);
        when(mapper.findActiveDepartmentName(10L)).thenReturn("投放二组");

        service.batchUpdateAssets(
                new AssetRequests.AssetBatchUpdate(
                        List.of(83L),
                        Set.of(AssetRequests.AssetBatchField.USAGE_TEAM),
                        Map.of(),
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        10L));

        verify(mapper)
                .updateAsset(
                        org.mockito.ArgumentMatchers.argThat(
                                value ->
                                        "1001".equals(value.getProjectId())
                                                && "项目 A".equals(value.getProjectName())
                                                && "投放二组".equals(value.getUsageTeam())
                                                && "ASSIGNED".equals(value.getStatus())));
    }
}
