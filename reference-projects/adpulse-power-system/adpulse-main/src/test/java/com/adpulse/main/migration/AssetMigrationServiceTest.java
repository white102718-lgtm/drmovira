package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.migration.AssetMigrationModels.*;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.SimpleTransactionStatus;

class AssetMigrationServiceTest {
    AssetMigrationMapper mapper = mock(AssetMigrationMapper.class);
    LegacyAssetReader reader = mock(LegacyAssetReader.class);
    AssetMigrationProperties properties = new AssetMigrationProperties();
    PlatformTransactionManager manager = mock(PlatformTransactionManager.class);
    ObjectMapper json = new ObjectMapper();
    ChannelMigrationMappingResolver mappings = mock(ChannelMigrationMappingResolver.class);
    AssetMigrationService service =
            new AssetMigrationService(mapper, reader, properties, json, manager, mappings);
    Job job;

    @BeforeEach
    void setup() {
        properties.setSourceUrl("jdbc:mysql://localhost/legacy");
        properties.setSourceUsername("readonly-test-user");
        properties.setSourcePassword("test-only-placeholder");
        properties.setTargetEnvironment(AssetMigrationProperties.TargetEnvironment.PRODUCTION);
        properties.setTargetUuid("17c4f6b3-a2cc-11f1-99a8-ea697aa9ac3a");
        properties.setOperatorIds(Set.of(7L));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                new CurrentUser(7L, "session", "operator", List.of()),
                                null,
                                List.of()));
        when(manager.getTransaction(any())).thenAnswer(invocation -> new SimpleTransactionStatus());
        when(mapper.identity())
                .thenReturn(new Identity(properties.getTargetUuid(), properties.getTargetSchema()));
        when(mapper.schemaReady()).thenReturn(1);
        when(mapper.activeOperator(7L)).thenReturn(1);
        when(mappings.resolve())
                .thenReturn(new ChannelSnapshot("production-version", Map.of(155L, 1L)));
        when(mapper.channels(anyBoolean())).thenReturn(List.of(new Channel(1, "ET224 ")));
        when(mapper.attributes()).thenReturn(List.of("普通户", "准稳户", "稳定户"));
        job = new Job();
        job.setId("test-job");
        job.setOperatorId(7);
        job.setState("QUEUED");
        when(mapper.nextJob()).thenReturn(job);
        when(mapper.job(job.getId())).thenReturn(job);
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void permissionCheckedBeforeAnyDatabaseAccess() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.plan()).isInstanceOf(AccessDeniedException.class);
        properties.setOperatorIds(Set.of());
        assertThatThrownBy(() -> service.status("id")).isInstanceOf(AccessDeniedException.class);
        verify(mapper, never()).lockMutex();
    }

    @Test
    void rejectsMissingSourceConfigurationBeforeCreatingAnyJob() {
        properties.setSourceUrl("");
        assertThatThrownBy(service::plan).hasMessageContaining("ASSET_MIGRATION_SOURCE_URL");
        verify(mapper, never()).insertJob(any());
        verify(mapper, never()).lockMutex();
    }

    @Test
    void failureDiagnosticKeepsLocationButNeverIncludesExceptionMessages() {
        var root = new IllegalArgumentException("password=do-not-output-this");
        root.setStackTrace(
                new StackTraceElement[] {
                    new StackTraceElement(
                            "com.adpulse.main.migration.LegacyAssetReader",
                            "initialize",
                            "LegacyAssetReader.java",
                            70)
                });
        String diagnostic =
                AssetMigrationService.safeDiagnostic(
                        new IllegalStateException("sensitive-url", root), "QUEUED");
        assertThat(diagnostic)
                .contains("QUEUED", "IllegalArgumentException", "LegacyAssetReader.java:70")
                .doesNotContain("password", "do-not-output", "sensitive-url");
    }

    @Test
    void testEnvironmentUsesItsOwnTargetChannelId() throws Exception {
        properties.setTargetEnvironment(AssetMigrationProperties.TargetEnvironment.TEST);
        properties.setTargetUuid("16903961-99f2-11f1-a1fe-86f52840e8b4");
        when(mapper.identity())
                .thenReturn(new Identity(properties.getTargetUuid(), properties.getTargetSchema()));
        when(mappings.resolve())
                .thenReturn(new ChannelSnapshot("test-version", Map.of(155L, 9900109L)));
        when(mapper.channels(anyBoolean())).thenReturn(List.of(new Channel(9900109L, "ET224 ")));
        prepareSingle();
        var desired = json.readValue(capturedItems().getFirst().getDesiredJson(), Values.class);
        assertThat(desired.channelId()).isEqualTo(9900109L);
        assertThat(job.getChannelHash()).isEqualTo("test-version");
        var environment = service.environment();
        assertThat(environment.targetEnvironment()).isEqualTo("TEST");
        assertThat(environment.channelLedgerTable()).isEqualTo("mig_channel_prod_test_batch");
    }

    @Test
    void environmentOrLedgerVersionChangeStopsBeforeNextBatch() {
        prepareSingle();
        job.setState("APPLYING");
        when(mappings.resolve())
                .thenReturn(new ChannelSnapshot("test-version", Map.of(155L, 9900109L)));
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getError()).contains("环境或渠道迁移账本已变化");
        verify(mapper, never()).insertAssets(anyList(), anyLong());
    }

    @Test
    void refusesWrongDatabaseBeforeCreatingJob() {
        when(mapper.identity()).thenReturn(new Identity("test-instance", "adpulse_system"));
        assertThatThrownBy(() -> service.plan()).hasMessageContaining("目标实例");
        verify(mapper, never()).insertJob(any());
    }

    @Test
    void refusesUnexpectedDefaultsAndRevokedOperator() {
        when(mapper.schemaReady()).thenReturn(0);
        assertThatThrownBy(() -> service.plan()).hasMessageContaining("默认值");
        when(mapper.schemaReady()).thenReturn(1);
        when(mapper.activeOperator(7L)).thenReturn(0);
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getError()).contains("操作员已失效");
        verifyNoInteractions(reader);
    }

    @Test
    void refusesCollationEquivalentButNonCanonicalTargetIds() {
        when(reader.read()).thenReturn(List.of(source(1, "123", null)));
        when(mapper.assets(anyList(), eq(false)))
                .thenReturn(List.of(new Asset(10, "１２３", 1L, "ET224 ", "企业户", null, 0, "before")));
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getError()).contains("非标准账户 ID");
        verify(mapper, never()).insertItems(anyList());
    }

    @Test
    void normalizesOnlyWhitespaceAndOneActPrefix() {
        assertThat(AssetMigrationService.normalize(" act_00123 ")).isEqualTo("00123");
        assertThat(AssetMigrationService.validAccountId("编号123")).isFalse();
        assertThat(AssetMigrationService.validAccountId("1e10")).isFalse();
        assertThat(
                        AssetMigrationService.validAccountId(
                                AssetMigrationService.normalize("act_act_123")))
                .isFalse();
        assertThat(AssetMigrationService.attribute(2)).isEqualTo("准稳户");
        assertThat(AssetMigrationService.attribute(3)).isEqualTo("稳定户");
        assertThat(AssetMigrationService.attribute(null)).isNull();
    }

    @Test
    void plansDuplicatesMissingAttributesConflictsAndSuspiciousIdsWithoutWritingAssets()
            throws Exception {
        when(reader.read())
                .thenReturn(
                        List.of(
                                source(1, " act_123 ", null),
                                source(2, "123", null),
                                source(3, "456", 1),
                                source(4, "BM-123", null),
                                source(5, "789", 3)));
        when(mapper.assets(anyList(), eq(false)))
                .thenReturn(
                        List.of(
                                new Asset(10, "123", 1L, "ET224 ", "企业户", "稳定户", 0, "before"),
                                new Asset(11, "456", 1L, "ET224 ", "企业户", "准稳户", 0, "before")));
        service.tick();
        var plans = capturedItems();
        assertThat(job.getState()).isEqualTo("READY");
        assertThat(job.getSourceCount()).isEqualTo(5);
        assertThat(job.getDuplicates()).isEqualTo(1);
        assertThat(job.getTotal()).isEqualTo(2);
        assertThat(job.getIsolated()).isEqualTo(2);
        Values desired = json.readValue(plans.getFirst().getDesiredJson(), Values.class);
        assertThat(desired.channelId()).isEqualTo(1);
        assertThat(desired.channelName()).isEqualTo("ET224 ");
        assertThat(desired.accountAttribute()).isEqualTo("稳定户");
        assertThat(plans.getFirst().getAction()).isEqualTo("UNCHANGED");
        assertThat(plans.get(1).getReason()).contains("属性冲突");
        assertThat(plans.get(3).getAction()).isEqualTo("INSERT");
        verify(mapper, never()).insertAssets(anyList(), anyLong());
        verify(mapper, never()).updateAssets(anyList());
    }

    @Test
    void isolatesAmbiguousSourcesTargetsAndManuallyLockedAssets() {
        when(reader.read())
                .thenReturn(
                        List.of(
                                source(1, "123", 1),
                                source(2, "123", 2),
                                source(3, "456", null),
                                source(4, "789", null)));
        when(mapper.assets(anyList(), eq(false)))
                .thenReturn(
                        List.of(
                                new Asset(10, "456", 1L, "ET224 ", "企业户", null, 0, "before"),
                                new Asset(11, "456", 1L, "ET224 ", "企业户", null, 0, "before"),
                                new Asset(12, "789", 1L, "ET224 ", "企业户", null, 1, "before")));
        service.tick();
        assertThat(capturedItems())
                .extracting(Item::getReason)
                .containsExactly("同一账户的来源五字段不一致", "目标存在多条有效资产", "目标已人工锁定");
    }

    @Test
    void missingChannelMappingBlocksWholePlan() {
        when(reader.read()).thenReturn(List.of(new Source(1, 999L, "123", "企业户", null, 0)));
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getError()).contains("映射不完整");
        verify(mapper, never()).insertItems(anyList());
        verify(manager).rollback(any());
    }

    @Test
    void requiresReviewedHashAndAcceptanceAndDoesNotExecuteInsideHttpRequest() {
        job.setState("READY");
        job.setPlanHash("hash");
        when(mapper.nextJob()).thenReturn(null);
        assertThatThrownBy(() -> service.execute(job.getId(), new Execute("wrong", true, true)))
                .hasMessageContaining("哈希");
        assertThatThrownBy(() -> service.execute(job.getId(), new Execute("hash", false, true)))
                .hasMessageContaining("AVAILABLE");
        assertThat(service.execute(job.getId(), new Execute("hash", true, true)).getState())
                .isEqualTo("VALIDATING");
        assertThat(service.execute(job.getId(), new Execute("hash", true, true)).getState())
                .isEqualTo("VALIDATING");
        verifyNoInteractions(reader);
        verify(mapper, never()).insertAssets(anyList(), anyLong());
    }

    @Test
    void sourceDriftStopsBeforeAnyAssetWrite() {
        job.setState("VALIDATING");
        job.setSourceHash("different");
        when(reader.read()).thenReturn(List.of(source(1, "123", 1)));
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getError()).contains("来源已变化");
        verify(mapper, never()).insertAssets(anyList(), anyLong());
    }

    @Test
    void targetDriftRollsBackAndKeepsProgressAtLastCommittedBatch() throws Exception {
        prepareSingle();
        Item item = capturedItems().getFirst();
        item.setId(1);
        job.setState("APPLYING");
        when(mapper.items(job.getId(), 0, "PENDING")).thenReturn(List.of(item));
        when(mapper.assets(anyList(), eq(true)))
                .thenReturn(List.of(new Asset(55, "123", 1L, "ET224 ", "企业户", null, 0, "new")));
        service.tick();
        assertThat(job.getState()).isEqualTo("FAILED");
        assertThat(job.getCompleted()).isZero();
        verify(mapper, never()).insertAssets(anyList(), anyLong());
        verify(mapper, never()).finishItems(anyList());
        verify(manager).rollback(any());
    }

    @Test
    void commitsAssetsAndAuditInOneRepeatableReadTransactionAndResumesFromPending()
            throws Exception {
        prepareSingle();
        Item item = capturedItems().getFirst();
        item.setId(1);
        job.setState("APPLYING");
        when(mapper.items(job.getId(), 0, "PENDING")).thenReturn(List.of(item), List.of());
        when(mapper.assets(anyList(), eq(true)))
                .thenReturn(
                        List.of(),
                        List.of(new Asset(55, "123", 1L, "ET224 ", "企业户", null, 0, "new")));
        when(mapper.insertAssets(anyList(), eq(7L))).thenReturn(1);
        service.tick();
        service.tick();
        assertThat(job.getState()).isEqualTo("DONE");
        assertThat(job.getCompleted()).isEqualTo(1);
        verify(mapper, times(1)).insertAssets(anyList(), eq(7L));
        var order = inOrder(mapper);
        order.verify(mapper).insertAssets(anyList(), eq(7L));
        order.verify(mapper).finishItems(anyList());
        order.verify(mapper).saveJob(job);
        assertThat(item.getTargetId()).isEqualTo(55L);
        assertThat(item.getAfterJson()).contains("ET224 ");
        verify(manager, atLeastOnce())
                .getTransaction(
                        argThat(
                                definition ->
                                        definition.getIsolationLevel()
                                                == TransactionDefinition
                                                        .ISOLATION_REPEATABLE_READ));
    }

    private void prepareSingle() {
        when(reader.read()).thenReturn(List.of(source(1, "123", null)));
        service.tick();
    }

    private List<Item> capturedItems() {
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Item>> captor = ArgumentCaptor.forClass(List.class);
        verify(mapper).insertItems(captor.capture());
        return captor.getValue();
    }

    private Source source(long id, String account, Integer attribute) {
        return new Source(id, 155L, account, "企业户", attribute, 0);
    }
}
