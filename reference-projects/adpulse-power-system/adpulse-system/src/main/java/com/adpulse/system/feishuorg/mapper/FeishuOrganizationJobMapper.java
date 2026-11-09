package com.adpulse.system.feishuorg.mapper;

import com.adpulse.system.feishuorg.model.FeishuOrganizationSchedule;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSyncLog;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 调度与认领 SQL；所有状态迁移在持有计划行锁的事务中执行。 */
@Mapper
public interface FeishuOrganizationJobMapper {
    FeishuOrganizationSchedule findSchedule();

    FeishuOrganizationSchedule lockSchedule();

    LocalDateTime now();

    int saveSchedule(FeishuOrganizationSchedule schedule);

    FeishuOrganizationSyncLog findJob(@Param("id") Long id);

    FeishuOrganizationSyncLog findActiveJob();

    int expireJobs();

    int claim(@Param("id") Long id);

    int retry(@Param("id") Long id, @Param("delaySeconds") int delaySeconds);
}
