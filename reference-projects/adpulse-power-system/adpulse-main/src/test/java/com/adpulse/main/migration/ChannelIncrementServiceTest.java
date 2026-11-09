package com.adpulse.main.migration;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.migration.AssetMigrationModels.ChannelSnapshot;
import com.adpulse.main.migration.AssetMigrationModels.Identity;
import com.adpulse.main.migration.AssetMigrationProperties.TargetEnvironment;
import com.adpulse.main.migration.ChannelIncrementModels.*;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class ChannelIncrementServiceTest {
    AssetMigrationMapper mapper = mock(AssetMigrationMapper.class);
    LegacyAssetReader reader = mock(LegacyAssetReader.class);
    ChannelMigrationMappingResolver mappings = mock(ChannelMigrationMappingResolver.class);
    AssetMigrationProperties properties = new AssetMigrationProperties();
    ChannelIncrementService service;

    @BeforeEach
    void setup() {
        properties.setTargetEnvironment(TargetEnvironment.TEST);
        properties.setTargetUuid("16903961-99f2-11f1-a1fe-86f52840e8b4");
        properties.setOperatorIds(Set.of(1L));
        when(mapper.identity())
                .thenReturn(new Identity(properties.getTargetUuid(), "adpulse_system"));
        when(mappings.resolveForChannelPlan())
                .thenReturn(new ChannelSnapshot("mapping-v1", Map.of(155L, 9900109L)));
        when(reader.readChannelSnapshot())
                .thenReturn(
                        new SourceSnapshot(
                                List.of(channel(155, "MPower-BM绑卡户"), channel(231, "MP118")),
                                List.of(rate(901, 231))));
        when(mapper.channelWriteSchemaReady()).thenReturn(1);
        service =
                new ChannelIncrementService(
                        mapper,
                        reader,
                        properties,
                        mappings,
                        new ObjectMapper().findAndRegisterModules());
        SecurityContextHolder.getContext()
                .setAuthentication(
                        UsernamePasswordAuthenticationToken.authenticated(
                                new CurrentUser(1L, "session", "operator", List.of()),
                                null,
                                List.of()));
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void planReturnsOnlyUnmappedChannelsAndStringIds() {
        Plan plan = service.plan(new PlanRequest(List.of()));

        assertThat(plan.environment()).isEqualTo("TEST");
        assertThat(plan.sourceCount()).isEqualTo(2);
        assertThat(plan.mappedCount()).isEqualTo(1);
        assertThat(plan.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.sourceId()).isEqualTo("231");
                            assertThat(item.channelName()).isEqualTo("MP118");
                            assertThat(item.rateCount()).isEqualTo(1);
                            assertThat(item.action()).isEqualTo("INSERT");
                        });
        assertThat(plan.planHash()).hasSize(64);
        verify(mapper).channelConflict("MP118", "C231");
    }

    @Test
    void executeRevalidatesPlanAndWritesChannelRateMappingAndBatch() {
        when(mapper.channelIncrementSchemaReady()).thenReturn(1);
        when(mapper.activeOperator(1L)).thenReturn(1);
        doAnswer(
                        invocation -> {
                            AppliedChannel candidate = invocation.getArgument(0);
                            candidate.setTargetId(5001L);
                            return 1;
                        })
                .when(mapper)
                .insertIncrementChannel(any(), eq(1L));
        Plan plan = service.plan(new PlanRequest(List.of("231")));

        ExecuteResult result =
                service.execute(new ExecuteRequest(List.of("231"), plan.planHash(), true));

        assertThat(result.environment()).isEqualTo("TEST");
        assertThat(result.channelCount()).isEqualTo(1);
        assertThat(result.rateCount()).isEqualTo(1);
        verify(mapper).insertIncrementChannel(any(), eq(1L));
        verify(mapper).insertIncrementRate(eq(5001L), any(), eq(1L));
        verify(mapper)
                .insertIncrementMapping(
                        eq("TEST"),
                        anyString(),
                        anyString(),
                        eq(properties.getTargetUuid()),
                        eq("adpulse_system"),
                        eq(231L),
                        eq(5001L),
                        startsWith("channel-increment-test-"),
                        eq(1L));
        verify(mapper)
                .insertIncrementBatch(
                        startsWith("channel-increment-test-"),
                        eq("TEST"),
                        eq(plan.planHash()),
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        eq(1L));
    }

    @Test
    void executeRejectsChangedPlanBeforeWriting() {
        when(mapper.channelIncrementSchemaReady()).thenReturn(1);

        assertThatThrownBy(() -> service.execute(new ExecuteRequest(List.of("231"), "old", true)))
                .hasMessageContaining("重新预检");
        verify(mapper, never()).insertIncrementChannel(any(), anyLong());
    }

    @Test
    void subsetUsesFullScanHashAndConflictsDoNotBlockOtherRows() {
        when(reader.readChannelSnapshot())
                .thenReturn(
                        new SourceSnapshot(
                                List.of(channel(231, "MP118"), channel(232, "Another")),
                                List.of()));
        when(mapper.channelConflict("Another", "C232"))
                .thenReturn(new TargetConflict(99L, "Another", "C232"));
        Plan all = service.plan(new PlanRequest(List.of()));
        Plan subset = service.plan(new PlanRequest(List.of("231")));
        assertThat(subset.planHash()).isEqualTo(all.planHash());
        assertThat(subset.items()).hasSize(1);
        assertThat(all.items().get(1).action()).isEqualTo("CONFLICT");
    }

    @Test
    void invalidChannelIsIsolatedFromOtherCandidates() {
        when(reader.readChannelSnapshot())
                .thenReturn(
                        new SourceSnapshot(
                                List.of(channel(231, "MP118"), channel(232, "")), List.of()));
        Plan all = service.plan(new PlanRequest(List.of()));
        assertThat(all.items().get(0).action()).isEqualTo("INSERT");
        assertThat(all.items().get(1).conflict()).contains("名称");
    }

    @Test
    void committedRetryReturnsOriginalResultWithoutReadingSource() {
        when(mapper.channelIncrementSchemaReady()).thenReturn(1);
        var result = new ExecuteResult("batch", "TEST", 1, 1);
        when(mapper.appliedChannelIncrement(
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        anyString(),
                        eq(1L),
                        eq("hash"),
                        eq("[\"231\"]")))
                .thenReturn(result);
        assertThat(service.execute(new ExecuteRequest(List.of("231"), "hash", true)))
                .isEqualTo(result);
        verify(reader, never()).readChannelSnapshot();
        verify(mapper, never()).insertIncrementChannel(any(), anyLong());
    }

    private static LegacyChannel channel(long id, String name) {
        return new LegacyChannel(
                id,
                name,
                name,
                "C" + id,
                1,
                "Mpower",
                1,
                "无",
                "USD",
                BigDecimal.ZERO,
                "address",
                "https://example.test",
                null,
                null,
                null,
                0,
                LocalDateTime.of(2026, 9, 14, 14, 1),
                LocalDateTime.of(2026, 9, 14, 14, 1));
    }

    private static LegacyRate rate(long id, long channelId) {
        return new LegacyRate(
                id,
                channelId,
                BigDecimal.ONE,
                BigDecimal.ZERO,
                LocalDate.of(2026, 1, 1),
                null,
                1,
                null,
                null,
                null,
                LocalDateTime.of(2026, 1, 1, 0, 0),
                null);
    }
}
