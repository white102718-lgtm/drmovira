package com.adpulse.system.feishuorg.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.feishuorg.client.FeishuOrganizationClient;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.*;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationJobMapper;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSchedule;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSyncLog;
import java.time.*;
import java.util.List;
import java.util.Objects;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

/** 持久化组织同步队列；短事务认领，外部读取后再持行锁校验并提交组织变更。 */
@Service
public class FeishuOrganizationJobService {
    private static final ZoneId BUSINESS_ZONE = ZoneId.of("Asia/Shanghai");
    private static final String READ =
            "hasAuthority('system:department:list') and hasAuthority('system:user:list')";
    private static final String WRITE =
            "hasAuthority('system:department:update') and hasAuthority('system:user:update')";
    private static final SyncResult EMPTY = new SyncResult(0, 0, 0, 0, 0, 0, 0, 0, 0, List.of());
    private final FeishuOrganizationJobMapper jobs;
    private final FeishuOrganizationMapper mapper;
    private final FeishuOrganizationClient client;
    private final FeishuOrganizationSafety safety;
    private final FeishuOrganizationSyncWriter writer;
    private final TransactionTemplate transaction;

    public FeishuOrganizationJobService(
            FeishuOrganizationJobMapper jobs,
            FeishuOrganizationMapper mapper,
            FeishuOrganizationClient client,
            FeishuOrganizationSafety safety,
            FeishuOrganizationSyncWriter writer,
            PlatformTransactionManager transactionManager) {
        this.jobs = jobs;
        this.mapper = mapper;
        this.client = client;
        this.safety = safety;
        this.writer = writer;
        this.transaction = new TransactionTemplate(transactionManager);
        this.transaction.setTimeout(120);
    }

    /** 返回计划，时间明确转换为北京时间。 */
    @PreAuthorize(READ)
    public ScheduleView schedule() {
        return view(requireSchedule(jobs.findSchedule()));
    }

    /** 保存计划；开启或修改开启中的计划时必须有当前操作者的有效预览。 */
    @PreAuthorize(WRITE)
    public ScheduleView saveSchedule(ScheduleSave request) {
        if (!List.of(0, 15, 30, 60).contains(request.intervalMinutes()))
            throw BusinessException.validation("同步间隔仅支持15、30、60分钟或每天");
        if (request.missingCountLimit() < 1
                || request.missingPercentLimit() < 1
                || request.missingPercentLimit() > 100)
            throw BusinessException.validation("缺失保护阈值不合法");
        try {
            LocalTime.parse(request.dailyTime());
        } catch (RuntimeException exception) {
            throw BusinessException.validation("每日执行时间格式应为HH:mm");
        }
        Long actor = SecurityContextHelper.currentUserId();
        return transaction.execute(
                status -> {
                    var schedule = requireSchedule(jobs.lockSchedule());
                    if (request.enabled()) {
                        var preview = requirePreview(request.previewId(), actor);
                        schedule.setVerifiedAppHash(preview.getAppHash());
                    }
                    schedule.setEnabled(request.enabled());
                    schedule.setIntervalMinutes(request.intervalMinutes());
                    schedule.setDailyTime(request.dailyTime());
                    schedule.setMissingCountLimit(request.missingCountLimit());
                    schedule.setMissingPercentLimit(request.missingPercentLimit());
                    schedule.setUpdatedBy(actor);
                    schedule.setNextRunAt(request.enabled() ? nextRun(schedule, jobs.now()) : null);
                    jobs.saveSchedule(schedule);
                    return view(schedule);
                });
    }

    /** 生成有时效和归属的预览；失败也保留记录，外部读取不占数据库事务。 */
    @PreAuthorize(READ)
    public Preview preview() {
        Long actor = SecurityContextHelper.currentUserId();
        var log = newLog("PREVIEW", "RUNNING", actor, null);
        mapper.insertLog(log);
        try {
            String appHash = safety.appHash();
            var snapshot = client.fetchSnapshot();
            if (!appHash.equals(safety.appHash()))
                throw BusinessException.conflict("飞书应用配置已变化，请重新预览");
            var assessment = safety.assess(snapshot, requireSchedule(jobs.findSchedule()));
            log.setAppHash(appHash);
            log.setSnapshotHash(assessment.hash());
            finish(
                    log,
                    assessment.result().conflictCount() == 0 ? "SUCCESS" : "REVIEW",
                    assessment.result(),
                    assessment.result().conflictCount() == 0
                            ? null
                            : String.join("；", assessment.result().conflicts()));
            return new Preview(
                    log.getId().toString(), assessment.result(), assessment.requiresReview());
        } catch (RuntimeException exception) {
            finish(log, "FAILED", EMPTY, "组织预览失败，请检查飞书应用权限、网络及组织数据完整性");
            throw BusinessException.conflict("组织预览失败，请检查飞书应用权限、网络及组织数据完整性");
        }
    }

    /** 提交手动任务，同一组织至多存在一个待执行或执行中的任务。 */
    @PreAuthorize(WRITE)
    public SyncSubmission submit(SyncRequest request) {
        Long actor = SecurityContextHelper.currentUserId();
        return transaction.execute(
                status -> {
                    requireSchedule(jobs.lockSchedule());
                    jobs.expireJobs();
                    if (jobs.findActiveJob() != null)
                        throw BusinessException.conflict("已有组织同步任务待执行或执行中");
                    var preview = requirePreview(request.previewId(), actor);
                    var job = newLog("MANUAL", "PENDING", actor, preview.getAppHash());
                    job.setSnapshotHash(preview.getSnapshotHash());
                    job.setAcceptMissing(request.acceptMissing());
                    mapper.insertLog(job);
                    return new SyncSubmission(job.getId().toString(), job.getStatus());
                });
    }

    /** 到期只提交一轮；服务停机错过的周期不逐个补跑。 */
    public void scheduleDue() {
        transaction.executeWithoutResult(
                status -> {
                    var schedule = requireSchedule(jobs.lockSchedule());
                    jobs.expireJobs();
                    LocalDateTime now = jobs.now();
                    if (!schedule.isEnabled()
                            || schedule.getNextRunAt() == null
                            || schedule.getNextRunAt().isAfter(now)) return;
                    var active = jobs.findActiveJob();
                    var job =
                            newLog(
                                    "SCHEDULED",
                                    active == null ? "PENDING" : "SKIPPED",
                                    null,
                                    schedule.getVerifiedAppHash());
                    mapper.insertLog(job);
                    if (active != null) finish(job, "SKIPPED", EMPTY, "上一轮同步尚未结束，本周期已跳过");
                    schedule.setNextRunAt(nextRun(schedule, now));
                    jobs.saveSchedule(schedule);
                });
    }

    /** 原子认领并消费一项任务，网络临时错误最多尝试三次。 */
    public void consumeOne() {
        var job =
                transaction.execute(
                        status -> {
                            requireSchedule(jobs.lockSchedule());
                            jobs.expireJobs();
                            var active = jobs.findActiveJob();
                            if (active == null || jobs.claim(active.getId()) != 1) return null;
                            return jobs.findJob(active.getId());
                        });
        if (job == null) return;
        try {
            if (!Objects.equals(job.getAppHash(), safety.appHash())) {
                review(job, "飞书应用配置已变化，自动同步已暂停，请重新预览并保存计划");
                return;
            }
            FeishuOrganizationSnapshot snapshot = client.fetchSnapshot();
            transaction.executeWithoutResult(status -> apply(job, snapshot));
        } catch (RuntimeException exception) {
            transaction.executeWithoutResult(
                    status -> {
                        requireSchedule(jobs.lockSchedule());
                        if (!owns(job)) return;
                        if (transientFailure(exception) && job.getAttempts() < 3) {
                            jobs.retry(job.getId(), job.getAttempts() == 1 ? 30 : 120);
                        } else {
                            finish(
                                    job,
                                    "FAILED",
                                    EMPTY,
                                    transientFailure(exception)
                                            ? "飞书连接失败，已达到重试上限，请检查网络后重试"
                                            : "组织同步失败，请检查应用权限和组织数据，重新预览后重试");
                        }
                    });
        }
    }

    private void apply(FeishuOrganizationSyncLog job, FeishuOrganizationSnapshot snapshot) {
        var schedule = requireSchedule(jobs.lockSchedule());
        if (!owns(job)) return;
        if (!Objects.equals(job.getAppHash(), safety.appHash())) {
            markReview(job, schedule, EMPTY, "应用配置在同步期间变化，请重新预览");
            return;
        }
        var assessment = safety.assess(snapshot, schedule);
        if (assessment.result().conflictCount() > 0) {
            markReview(
                    job,
                    schedule,
                    assessment.result(),
                    String.join("；", assessment.result().conflicts()));
            return;
        }
        if ("MANUAL".equals(job.getTriggerType())
                && !Objects.equals(job.getSnapshotHash(), assessment.hash())) {
            markReview(job, schedule, assessment.result(), "组织数据已变化，本次未写入，请重新预览并确认");
            return;
        }
        if (assessment.requiresReview()
                && !("MANUAL".equals(job.getTriggerType()) && job.isAcceptMissing())) {
            markReview(job, schedule, assessment.result(), "缺失停用达到保护阈值，本次未写入；请预览核查并人工确认");
            return;
        }
        var result = writer.synchronize(snapshot, job.getStartedBy(), new java.util.ArrayList<>());
        if (result.conflictCount() > 0 || !owns(job))
            throw BusinessException.conflict("同步校验失败或执行租约已过期");
        // 与组织写入同一事务提交，避免业务成功却被重试或标记失败。
        finish(job, "SUCCESS", result, null);
    }

    private void review(FeishuOrganizationSyncLog job, String reason) {
        transaction.executeWithoutResult(
                status -> {
                    var schedule = requireSchedule(jobs.lockSchedule());
                    if (owns(job)) markReview(job, schedule, EMPTY, reason);
                });
    }

    private void markReview(
            FeishuOrganizationSyncLog job,
            FeishuOrganizationSchedule schedule,
            SyncResult result,
            String reason) {
        finish(job, "REVIEW", result, reason);
        if ("SCHEDULED".equals(job.getTriggerType())) {
            schedule.setEnabled(false);
            schedule.setNextRunAt(null);
            jobs.saveSchedule(schedule);
        }
    }

    private boolean owns(FeishuOrganizationSyncLog job) {
        var current = jobs.findJob(job.getId());
        return current != null
                && "RUNNING".equals(current.getStatus())
                && current.getAttempts() == job.getAttempts()
                && current.getLeaseUntil() != null
                && current.getLeaseUntil().isAfter(jobs.now());
    }

    private FeishuOrganizationSyncLog requirePreview(String id, Long actor) {
        Long previewId;
        try {
            previewId = Long.valueOf(id);
        } catch (RuntimeException exception) {
            throw BusinessException.validation("请先生成同步预览");
        }
        var preview = jobs.findJob(previewId);
        if (preview == null
                || !"PREVIEW".equals(preview.getTriggerType())
                || !"SUCCESS".equals(preview.getStatus())
                || !Objects.equals(preview.getStartedBy(), actor)
                || preview.getAvailableAt() == null
                || !preview.getAvailableAt().plusMinutes(15).isAfter(jobs.now())
                || preview.getSnapshotHash() == null
                || !Objects.equals(preview.getAppHash(), safety.appHash())) {
            throw BusinessException.conflict("预览无效、已过期或应用已变化，请重新预览（有效期15分钟）");
        }
        return preview;
    }

    private boolean transientFailure(RuntimeException exception) {
        return exception instanceof ResourceAccessException
                || exception instanceof HttpServerErrorException
                || exception instanceof HttpClientErrorException.TooManyRequests;
    }

    private FeishuOrganizationSyncLog newLog(
            String trigger, String status, Long actor, String appHash) {
        var log = new FeishuOrganizationSyncLog();
        log.setTriggerType(trigger);
        log.setStatus(status);
        log.setStartedBy(actor);
        log.setAppHash(appHash);
        return log;
    }

    private void finish(
            FeishuOrganizationSyncLog job, String status, SyncResult result, String error) {
        job.setStatus(status);
        job.setResult(result);
        job.setErrorMessage(
                error == null ? null : error.substring(0, Math.min(1000, error.length())));
        mapper.finishLog(job);
    }

    private FeishuOrganizationSchedule requireSchedule(FeishuOrganizationSchedule schedule) {
        if (schedule == null) throw BusinessException.conflict("组织同步计划未初始化，请先执行V39数据库脚本");
        return schedule;
    }

    private ScheduleView view(FeishuOrganizationSchedule schedule) {
        return new ScheduleView(
                schedule.isEnabled(),
                schedule.getIntervalMinutes(),
                schedule.getDailyTime(),
                schedule.getMissingCountLimit(),
                schedule.getMissingPercentLimit(),
                schedule.getNextRunAt() == null
                        ? null
                        : schedule.getNextRunAt()
                                .atOffset(ZoneOffset.UTC)
                                .atZoneSameInstant(BUSINESS_ZONE)
                                .toOffsetDateTime());
    }

    /** UTC 存储，每日时间按北京时间计算；跨天不受服务器默认时区影响。 */
    static LocalDateTime nextRun(FeishuOrganizationSchedule schedule, LocalDateTime now) {
        if (schedule.getIntervalMinutes() > 0)
            return now.plusMinutes(schedule.getIntervalMinutes());
        var localNow = now.atOffset(ZoneOffset.UTC).atZoneSameInstant(BUSINESS_ZONE);
        var next =
                localNow.toLocalDate()
                        .atTime(LocalTime.parse(schedule.getDailyTime()))
                        .atZone(BUSINESS_ZONE);
        if (!next.isAfter(localNow)) next = next.plusDays(1);
        return LocalDateTime.ofInstant(next.toInstant(), ZoneOffset.UTC);
    }
}
