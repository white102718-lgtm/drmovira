package com.adpulse.main.google.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.google.client.GoogleProviderClient;
import com.adpulse.main.google.mapper.GoogleIntegrationMapper;
import com.adpulse.main.google.model.GoogleModels.Mapping;
import com.adpulse.main.google.model.GoogleModels.SyncData;
import com.adpulse.main.google.model.GoogleModels.SyncJob;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** Google映射全量同步与任务状态测试。 */
@ExtendWith(MockitoExtension.class)
class GoogleIntegrationSyncServiceTest {
    @Mock private GoogleIntegrationMapper mapper;
    @Mock private GoogleIntegrationService integrationService;
    @Mock private GoogleProviderClient provider;

    private GoogleIntegrationSyncService service;

    @BeforeEach
    void setUp() {
        service =
                new GoogleIntegrationSyncService(
                        mapper, integrationService, provider, new ObjectMapper());
    }

    @Test
    void shouldConsumeFullSyncAndUpsertMappedRows() {
        SyncJob job = job();
        Mapping mapping = mapping();
        when(mapper.findPendingSyncJobs(10)).thenReturn(List.of(job));
        when(mapper.claimSyncJob(9L)).thenReturn(1);
        when(mapper.findMapping(1L)).thenReturn(mapping);
        when(integrationService.accessTokenForSync(mapping)).thenReturn("token");
        when(provider.values("token", "sheet-file", "工作表1"))
                .thenReturn(
                        List.of(
                                List.of("日期", "项目", "任务线", "媒体", "花费"),
                                List.of("2026/8/24", "项目A", "任务线A", "GG", "1,234.50")));

        service.consumePendingJobs();

        ArgumentCaptor<SyncData> captor = ArgumentCaptor.forClass(SyncData.class);
        verify(mapper).upsertSyncData(captor.capture());
        assertThat(captor.getValue().getStartDate()).isEqualTo(LocalDate.of(2026, 8, 24));
        assertThat(captor.getValue().getSpendAmount())
                .isEqualByComparingTo(new BigDecimal("1234.50"));
        assertThat(captor.getValue().getMediaPlacement()).isEqualTo("Google");
        verify(mapper).updateMappingLastSyncTime(1L);
        verify(mapper).completeSyncJob(9L);
    }

    @Test
    void shouldFailUnsupportedWriteJobWithoutMarkingSuccess() {
        SyncJob job = job();
        Mapping mapping = mapping();
        mapping.setSyncDirection(2);
        when(mapper.findPendingSyncJobs(10)).thenReturn(List.of(job));
        when(mapper.claimSyncJob(9L)).thenReturn(1);
        when(mapper.findMapping(1L)).thenReturn(mapping);

        service.consumePendingJobs();

        verify(mapper).failSyncJob(eq(9L), anyString());
    }

    private SyncJob job() {
        SyncJob job = new SyncJob();
        job.setId(9L);
        job.setBusinessId("1");
        job.setRequestPayload("{\"fullSync\":true}");
        job.setRequestedBy(1L);
        return job;
    }

    private Mapping mapping() {
        Mapping mapping = new Mapping();
        mapping.setId(1L);
        mapping.setGoogleAccountId(1L);
        mapping.setSpreadsheetId("sheet-file");
        mapping.setSheetNames("[\"工作表1\"]");
        mapping.setFieldMappings(
                "{\"工作表1\":["
                        + "{\"systemField\":\"startDate\",\"sheetColumn\":\"A\"},"
                        + "{\"systemField\":\"taskName\",\"sheetColumn\":\"B\"},"
                        + "{\"systemField\":\"subtaskName\",\"sheetColumn\":\"C\"},"
                        + "{\"systemField\":\"mediaPlacement\",\"sheetColumn\":\"D\"},"
                        + "{\"systemField\":\"spendAmount\",\"sheetColumn\":\"E\"}]}");
        mapping.setSyncDirection(1);
        mapping.setEnableFlag(1);
        mapping.setDateRangeType(2);
        mapping.setDateRangeConfig("{\"days\":7}");
        return mapping;
    }
}
