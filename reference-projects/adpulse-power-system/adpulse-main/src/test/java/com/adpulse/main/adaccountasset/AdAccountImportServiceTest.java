package com.adpulse.main.adaccountasset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.adaccountasset.AdAccountAssetRequests.ImportItem;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportFailure;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportResult;
import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
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

/** 广告账户导入记录加密与用户隔离测试。 */
@ExtendWith(MockitoExtension.class)
class AdAccountImportServiceTest {
    @Mock private AdAccountAssetService assetService;
    @Mock private AdAccountAssetMapper mapper;
    @Mock private AdAccountImportCodec codec;
    @Mock private IntegrationSecretCipher cipher;

    private AdAccountImportService service;

    @BeforeEach
    void setUp() {
        service =
                new AdAccountImportService(assetService, mapper, codec, cipher, new ObjectMapper());
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
    void shouldEncryptFailureWorkbookAndExcludeOriginalCellsFromFailureJson() {
        ImportItem item =
                new ImportItem(
                        2,
                        "secret-account",
                        "secret-name",
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
                        null);
        var row = new AdAccountImportCodec.ParsedRow(2, List.of("secret-account"), item);
        var parsed = new AdAccountImportCodec.ParsedFile(List.of("*账户ID"), List.of(row));
        when(codec.read(any(), any())).thenReturn(parsed);
        when(assetService.importAccounts(List.of(item)))
                .thenReturn(
                        new ImportResult(
                                1, 0, List.of(new ImportFailure(2, "secret-account", "渠道不存在"))));
        when(codec.writeFailures(any(), any())).thenReturn(new byte[] {1, 2, 3});
        when(cipher.encrypt(any())).thenReturn("encrypted-workbook");

        service.importFile(new byte[] {9}, "账户.csv");

        ArgumentCaptor<AdAccountImportLog> logCaptor =
                ArgumentCaptor.forClass(AdAccountImportLog.class);
        verify(mapper).insertImportLog(logCaptor.capture());
        assertThat(logCaptor.getValue().getFailedFileCiphertext()).isEqualTo("encrypted-workbook");
        assertThat(logCaptor.getValue().getFailureDetails())
                .contains("渠道不存在")
                .doesNotContain("secret-account", "secret-name");
    }

    @Test
    void shouldScopeHistoryAndFailureDownloadToCurrentOperator() {
        when(mapper.findImportLogsByOperatorId(7L)).thenReturn(List.of());

        assertThat(service.history()).isEmpty();
        assertThatThrownBy(() -> service.failedFile(99L))
                .isInstanceOf(AdAccountAssetService.AdAccountAssetException.class)
                .hasMessageContaining("导入记录不存在");
        verify(mapper).findImportLogsByOperatorId(7L);
        verify(mapper).findImportLogByIdAndOperatorId(99L, 7L);
    }
}
