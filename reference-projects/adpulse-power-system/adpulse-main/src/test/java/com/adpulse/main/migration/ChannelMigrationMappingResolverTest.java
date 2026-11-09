package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.migration.AssetMigrationModels.ChannelLedger;
import com.adpulse.main.migration.AssetMigrationProperties.TargetEnvironment;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.HashMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

class ChannelMigrationMappingResolverTest {
    static final String PROD_UUID = "17c4f6b3-a2cc-11f1-99a8-ea697aa9ac3a";
    static final String TEST_UUID = "16903961-99f2-11f1-a1fe-86f52840e8b4";
    AssetMigrationMapper mapper = mock(AssetMigrationMapper.class);
    AssetMigrationProperties properties = new AssetMigrationProperties();
    StringRedisTemplate redis = mock(StringRedisTemplate.class);

    @SuppressWarnings("unchecked")
    ValueOperations<String, String> values = mock(ValueOperations.class);

    HashMap<String, String> cache = new HashMap<>();
    ChannelMigrationMappingResolver resolver =
            new ChannelMigrationMappingResolver(mapper, properties, new ObjectMapper(), redis);

    @BeforeEach
    void setup() {
        properties.setTargetEnvironment(TargetEnvironment.PRODUCTION);
        properties.setTargetUuid(PROD_UUID);
        when(redis.opsForValue()).thenReturn(values);
        when(values.get(anyString()))
                .thenAnswer(invocation -> cache.get(invocation.getArgument(0)));
        doAnswer(
                        invocation -> {
                            cache.put(invocation.getArgument(0), invocation.getArgument(1));
                            return null;
                        })
                .when(values)
                .set(anyString(), anyString(), eq(Duration.ofMinutes(10)));
        fixture(1);
    }

    @Test
    void emptyMappingAllowsChannelBootstrapButNeverAccountMigration() {
        when(mapper.ledgerExists("PRODUCTION")).thenReturn(0);
        when(mapper.channelIncrementSchemaReady()).thenReturn(1);
        assertThat(resolver.resolveForChannelPlan().ids()).isEmpty();
        assertThatThrownBy(resolver::resolve).hasMessageContaining("先同步渠道");
    }

    @Test
    void damagedCombinedCacheFallsBackToVerifiedDatabase() {
        when(mapper.channelIncrementSchemaReady()).thenReturn(1);
        resolver.resolve();
        cache.replaceAll((key, value) -> "broken-json");
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
    }

    @Test
    void cachesOnlyIdProjectionButChecksDatabaseLedgerOnEveryRead() {
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
        verify(mapper, times(2)).channelLedger("PRODUCTION", properties.channelBatchKey());
        verify(mapper, times(1)).channelMapping("PRODUCTION", properties.channelBatchKey());
        assertThat(cache).hasSize(1);
        assertThat(cache.values().iterator().next())
                .doesNotContain("account", "password", "rate", "channel_name");
    }

    @Test
    void sameRedisKeepsTestAndProductionMappingsSeparate() {
        var production = resolver.resolve();
        properties.setTargetEnvironment(TargetEnvironment.TEST);
        properties.setTargetUuid(TEST_UUID);
        fixture(9900109);
        var test = resolver.resolve();
        assertThat(production.ids()).containsEntry(155L, 1L);
        assertThat(test.ids()).containsEntry(155L, 9900109L);
        assertThat(test.version()).isNotEqualTo(production.version());
        assertThat(cache).hasSize(2);
        assertThat(cache.keySet())
                .anyMatch(key -> key.contains(":TEST:"))
                .anyMatch(key -> key.contains(":PRODUCTION:"));
        verify(mapper).channelMapping("TEST", "mpower-prod-to-test-channels-v1");
    }

    @Test
    void payloadRevisionGetsNewCacheVersion() {
        var first = resolver.resolve();
        fixture(2);
        var second = resolver.resolve();
        assertThat(second.version()).isNotEqualTo(first.version());
        assertThat(second.ids()).containsEntry(155L, 2L);
        assertThat(cache).hasSize(2);
    }

    @Test
    void rollbackOrMissingTableRejectsEvenWithWarmCache() {
        resolver.resolve();
        when(mapper.channelLedger("PRODUCTION", properties.channelBatchKey())).thenReturn(null);
        assertThatThrownBy(resolver::resolve).hasMessageContaining("已回滚");
        when(mapper.ledgerExists("PRODUCTION")).thenReturn(0);
        assertThatThrownBy(resolver::resolve).hasMessageContaining("尚未创建");
        verify(values, times(1)).get(anyString());
    }

    @Test
    void copiedLedgerFromAnotherTargetIsRejectedBeforeCacheLookup() {
        var ledger = ledger("[]");
        when(mapper.channelLedger("PRODUCTION", properties.channelBatchKey()))
                .thenReturn(
                        new ChannelLedger(
                                ledger.sourceFingerprint(),
                                "test-fingerprint",
                                ledger.payloadHash(),
                                ledger.mappingHash()));
        assertThatThrownBy(resolver::resolve).hasMessageContaining("目标实例不符");
        verifyNoInteractions(redis);
    }

    @Test
    void wrongSourceFingerprintIsRejected() {
        var ledger = ledger("[]");
        when(mapper.channelLedger("PRODUCTION", properties.channelBatchKey()))
                .thenReturn(
                        new ChannelLedger(
                                "other-source",
                                ledger.targetFingerprint(),
                                ledger.payloadHash(),
                                ledger.mappingHash()));
        assertThatThrownBy(resolver::resolve).hasMessageContaining("来源实例不符");
        verifyNoInteractions(redis);
    }

    @Test
    void corruptCacheIsReplacedFromDatabase() {
        resolver.resolve();
        cache.replaceAll((key, value) -> "[{\"sourceId\":155,\"targetId\":999}]");
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
        verify(mapper, times(2)).channelMapping("PRODUCTION", properties.channelBatchKey());
        assertThat(cache.values().iterator().next()).doesNotContain("999");
    }

    @Test
    void redisOutageFallsBackToDatabaseAndDisabledCacheNeverTouchesRedis() {
        when(values.get(anyString())).thenThrow(new IllegalStateException("offline"));
        doThrow(new IllegalStateException("offline"))
                .when(values)
                .set(anyString(), anyString(), any(Duration.class));
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
        properties.setMappingCacheEnabled(false);
        clearInvocations(redis, values);
        assertThat(resolver.resolve().ids()).containsEntry(155L, 1L);
        verifyNoInteractions(redis, values);
    }

    @Test
    void duplicateOrNonNumericMappingIsRejected() {
        for (String projection :
                new String[] {
                    "[{\"sourceId\":155,\"targetId\":1},{\"sourceId\":155,\"targetId\":2}]",
                    "[{\"sourceId\":155,\"targetId\":1},{\"sourceId\":156,\"targetId\":1}]",
                    "[{\"sourceId\":\"bad\",\"targetId\":1}]"
                }) {
            when(mapper.channelLedger("PRODUCTION", properties.channelBatchKey()))
                    .thenReturn(ledger(projection));
            when(mapper.channelMapping("PRODUCTION", properties.channelBatchKey()))
                    .thenReturn(projection);
            assertThatThrownBy(resolver::resolve)
                    .isInstanceOf(AssetMigrationService.Conflict.class);
        }
        assertThat(cache).isEmpty();
    }

    @Test
    void fingerprintMatchesExistingPythonTestLedger() {
        assertThat(ChannelMigrationMappingResolver.fingerprint(TEST_UUID, "adpulse_system"))
                .isEqualTo("9e6315a4d110ba982488b599bc9559ade164b8e75e628d3863687180181d7182");
    }

    @Test
    void knownProductionInstanceCannotBeConfiguredAsTest() {
        properties.setTargetEnvironment(TargetEnvironment.TEST);
        assertThatThrownBy(resolver::resolve).hasMessageContaining("已知实例不符");
    }

    private void fixture(long targetId) {
        String projection = "[{\"sourceId\":155,\"targetId\":" + targetId + "}]";
        String environment = properties.getTargetEnvironment().name();
        when(mapper.ledgerExists(environment)).thenReturn(1);
        when(mapper.channelLedger(environment, properties.channelBatchKey()))
                .thenReturn(ledger(projection));
        when(mapper.channelMapping(environment, properties.channelBatchKey()))
                .thenReturn(projection);
    }

    private ChannelLedger ledger(String projection) {
        return new ChannelLedger(
                ChannelMigrationMappingResolver.fingerprint(
                        properties.getSourceUuid(), properties.getSourceSchema()),
                ChannelMigrationMappingResolver.fingerprint(
                        properties.getTargetUuid(), properties.getTargetSchema()),
                ChannelMigrationMappingResolver.sha256("payload-" + projection),
                ChannelMigrationMappingResolver.sha256(projection));
    }
}
