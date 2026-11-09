package com.adpulse.system.feishuorg.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.feishuorg.client.FeishuOrganizationClient;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.*;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationJobMapper;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.*;
import com.adpulse.system.feishuorg.service.FeishuOrganizationSafety.Assessment;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.web.client.ResourceAccessException;

/** 调度去重、租约隔离、人工确认、错误重试和权限边界测试。 */
class FeishuOrganizationJobServiceTest {
    private final FeishuOrganizationJobMapper jobs = mock(FeishuOrganizationJobMapper.class);
    private final FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
    private final FeishuOrganizationClient client = mock(FeishuOrganizationClient.class);
    private final FeishuOrganizationSafety safety = mock(FeishuOrganizationSafety.class);
    private final FeishuOrganizationSyncWriter writer = mock(FeishuOrganizationSyncWriter.class);
    private final PlatformTransactionManager transactions = mock(PlatformTransactionManager.class);
    private final FeishuOrganizationJobService service =
            new FeishuOrganizationJobService(jobs, mapper, client, safety, writer, transactions);
    private final LocalDateTime now = LocalDateTime.of(2026, 9, 7, 1, 0);
    private final SyncResult result = new SyncResult(1, 0, 1, 0, 5, 0, 4, 1, 0, List.of());
    private final FeishuOrganizationSnapshot snapshot =
            new FeishuOrganizationSnapshot("tenant", List.of(), List.of());
    private FeishuOrganizationSchedule schedule;
    private FeishuOrganizationSyncLog job;

    @BeforeEach
    void setup() {
        when(transactions.getTransaction(any()))
                .thenAnswer(invocation -> new SimpleTransactionStatus());
        schedule = new FeishuOrganizationSchedule();
        schedule.setEnabled(true);
        schedule.setIntervalMinutes(60);
        schedule.setDailyTime("02:00");
        schedule.setVerifiedAppHash("app");
        schedule.setMissingCountLimit(10);
        schedule.setMissingPercentLimit(20);
        schedule.setNextRunAt(now.minusHours(5));
        when(jobs.lockSchedule()).thenReturn(schedule);
        when(jobs.findSchedule()).thenReturn(schedule);
        when(jobs.now()).thenReturn(now);
        when(safety.appHash()).thenReturn("app");
        job = new FeishuOrganizationSyncLog();
        job.setId(8L);
        job.setTriggerType("SCHEDULED");
        job.setStatus("RUNNING");
        job.setAttempts(1);
        job.setAppHash("app");
        job.setLeaseUntil(now.plusMinutes(15));
        when(jobs.findActiveJob()).thenReturn(job);
        when(jobs.claim(8L)).thenReturn(1);
        when(jobs.findJob(8L)).thenReturn(job);
        when(client.fetchSnapshot()).thenReturn(snapshot);
        when(safety.assess(snapshot, schedule))
                .thenReturn(new Assessment(result, false, "snapshot"));
        when(writer.synchronize(eq(snapshot), isNull(), anyList())).thenReturn(result);
        authenticate(List.of());
    }

    @AfterEach
    void clearIdentity() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void scheduledSyncSucceedsWithoutLoginIdentity() {
        SecurityContextHolder.clearContext();
        service.consumeOne();
        verify(writer).synchronize(eq(snapshot), isNull(), anyList());
        assertThat(job.getStatus()).isEqualTo("SUCCESS");
        verify(mapper).finishLog(job);
    }

    @Test
    void failedClaimDoesNotFetchOrWrite() {
        when(jobs.claim(8L)).thenReturn(0);
        service.consumeOne();
        verifyNoInteractions(client, writer);
    }

    @Test
    void expiredWorkerCannotWriteOrOverrideRecoveredJob() {
        when(client.fetchSnapshot())
                .thenAnswer(
                        invocation -> {
                            job.setLeaseUntil(now.minusSeconds(1));
                            return snapshot;
                        });
        service.consumeOne();
        verifyNoInteractions(writer);
        verify(mapper, never()).finishLog(any());
    }

    @Test
    void changedAttemptFencesStaleWorker() {
        var recovered = new FeishuOrganizationSyncLog();
        recovered.setStatus("RUNNING");
        recovered.setAttempts(2);
        recovered.setLeaseUntil(now.plusMinutes(15));
        when(jobs.findJob(8L)).thenReturn(job, recovered);
        service.consumeOne();
        verifyNoInteractions(writer);
    }

    @Test
    void excessiveMissingDataPausesAutomaticSyncWithoutWriting() {
        when(safety.assess(snapshot, schedule))
                .thenReturn(new Assessment(result, true, "snapshot"));
        service.consumeOne();
        assertThat(job.getStatus()).isEqualTo("REVIEW");
        assertThat(schedule.isEnabled()).isFalse();
        assertThat(schedule.getNextRunAt()).isNull();
        verifyNoInteractions(writer);
    }

    @Test
    void manualConfirmationOnlyAcceptsMatchingPreview() {
        job.setTriggerType("MANUAL");
        job.setSnapshotHash("old");
        job.setAcceptMissing(true);
        service.consumeOne();
        assertThat(job.getStatus()).isEqualTo("REVIEW");
        verifyNoInteractions(writer);
    }

    @Test
    void confirmedMatchingManualPreviewMayApplyMissingChanges() {
        job.setTriggerType("MANUAL");
        job.setSnapshotHash("snapshot");
        job.setAcceptMissing(true);
        when(safety.assess(snapshot, schedule))
                .thenReturn(new Assessment(result, true, "snapshot"));
        service.consumeOne();
        assertThat(job.getStatus()).isEqualTo("SUCCESS");
    }

    @Test
    void retriesOnlyTemporaryReadFailuresAndStopsAfterThreeAttempts() {
        when(client.fetchSnapshot()).thenThrow(new ResourceAccessException("temporary"));
        service.consumeOne();
        verify(jobs).retry(8L, 30);
        job.setAttempts(3);
        service.consumeOne();
        assertThat(job.getStatus()).isEqualTo("FAILED");
        verifyNoInteractions(writer);
    }

    @Test
    void validationFailureIsNotRetriedAndWriteFailureRollsBack() {
        when(writer.synchronize(eq(snapshot), isNull(), anyList()))
                .thenThrow(BusinessException.conflict("冲突"));
        service.consumeOne();
        verify(transactions).rollback(any());
        verify(jobs, never()).retry(anyLong(), anyInt());
        assertThat(job.getStatus()).isEqualTo("FAILED");
    }

    @Test
    void configurationChangePausesWithoutReadingRemoteData() {
        when(safety.appHash()).thenReturn("changed");
        service.consumeOne();
        assertThat(job.getStatus()).isEqualTo("REVIEW");
        verifyNoInteractions(client, writer);
    }

    @Test
    void missedCyclesProduceOneJobAndActiveJobIsSkipped() {
        service.scheduleDue();
        verify(mapper).insertLog(argThat(log -> "SKIPPED".equals(log.getStatus())));
        assertThat(schedule.getNextRunAt()).isEqualTo(now.plusHours(1));
        when(jobs.findActiveJob()).thenReturn(null);
        schedule.setNextRunAt(now.minusDays(3));
        service.scheduleDue();
        verify(mapper).insertLog(argThat(log -> "PENDING".equals(log.getStatus())));
    }

    @Test
    void dailyScheduleUsesBeijingTimeAcrossUtcDateBoundary() {
        schedule.setIntervalMinutes(0);
        schedule.setDailyTime("02:00");
        assertThat(
                        FeishuOrganizationJobService.nextRun(
                                schedule, LocalDateTime.of(2026, 9, 7, 17, 0)))
                .isEqualTo(LocalDateTime.of(2026, 9, 7, 18, 0));
        assertThat(
                        FeishuOrganizationJobService.nextRun(
                                schedule, LocalDateTime.of(2026, 9, 7, 18, 0)))
                .isEqualTo(LocalDateTime.of(2026, 9, 8, 18, 0));
    }

    @Test
    void manualSubmitRejectsActiveJobAndExpiredOrOtherUsersPreview() {
        assertThatThrownBy(() -> service.submit(new SyncRequest("9", false)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("已有");
        when(jobs.findActiveJob()).thenReturn(null);
        var preview = new FeishuOrganizationSyncLog();
        preview.setStatus("SUCCESS");
        preview.setTriggerType("PREVIEW");
        preview.setStartedBy(7L);
        preview.setAvailableAt(now.minusMinutes(16));
        preview.setAppHash("app");
        preview.setSnapshotHash("snapshot");
        when(jobs.findJob(9L)).thenReturn(preview);
        assertThatThrownBy(() -> service.submit(new SyncRequest("9", false)))
                .hasMessageContaining("预览无效");
        preview.setAvailableAt(now);
        preview.setStartedBy(99L);
        assertThatThrownBy(() -> service.submit(new SyncRequest("9", true)))
                .hasMessageContaining("预览无效");
        verify(mapper, never()).insertLog(any());
    }

    @Test
    void disablingDoesNotNeedPreviewAndEnablingRequiresOne() {
        service.saveSchedule(new ScheduleSave(false, 60, "02:00", 10, 20, null));
        assertThat(schedule.getNextRunAt()).isNull();
        assertThatThrownBy(
                        () ->
                                service.saveSchedule(
                                        new ScheduleSave(true, 60, "02:00", 10, 20, null)))
                .hasMessageContaining("预览");
    }

    @Test
    void readOnlyAccountCannotSaveOrSubmitThroughServiceProxy() {
        authenticate(List.of("system:user:list", "system:department:list"));
        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(SecurityConfiguration.class);
            context.registerBean(FeishuOrganizationJobService.class, () -> service);
            context.refresh();
            var secured = context.getBean(FeishuOrganizationJobService.class);
            assertThat(secured.schedule()).isNotNull();
            assertThatThrownBy(
                            () ->
                                    secured.saveSchedule(
                                            new ScheduleSave(false, 60, "02:00", 10, 20, null)))
                    .isInstanceOf(AccessDeniedException.class);
            assertThatThrownBy(() -> secured.submit(new SyncRequest("9", true)))
                    .isInstanceOf(AccessDeniedException.class);
        }
    }

    private void authenticate(List<String> permissions) {
        var user =
                new CurrentUser(
                        7L,
                        "session",
                        "测试用户",
                        Set.copyOf(permissions.stream().map(SimpleGrantedAuthority::new).toList()));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                user,
                                "",
                                permissions.stream().map(SimpleGrantedAuthority::new).toList()));
    }

    @Configuration
    @EnableMethodSecurity
    static class SecurityConfiguration {}
}
