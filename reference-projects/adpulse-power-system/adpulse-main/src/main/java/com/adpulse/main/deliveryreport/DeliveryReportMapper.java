package com.adpulse.main.deliveryreport;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 投放日报及有效业务归属的 MySQL 访问。 */
@Mapper
public interface DeliveryReportMapper {
    List<DeliveryReportRecord> findReadRecords(
            @Param("userId") Long userId,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate,
            @Param("reporter") String reporter,
            @Param("project") String project,
            @Param("line") String line,
            @Param("limit") Integer limit,
            @Param("offset") long offset);

    long countReadRecords(
            @Param("userId") Long userId,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate,
            @Param("reporter") String reporter,
            @Param("project") String project,
            @Param("line") String line);

    /** 按ID批量读取当前用户可见的已保存日报，供外部推送重新校验。 */
    List<DeliveryReportRecord> findReadRecordsByIds(
            @Param("userId") Long userId, @Param("ids") List<Long> ids);

    List<ReportAttachment> findReadAttachments(@Param("ids") List<Long> ids);

    List<Reporter> findReporters(@Param("userId") Long userId);

    /** 人员导航仅列出具有有效投放师角色的用户，空用户ID表示管理角色的全员范围。 */
    List<Reporter> findOperatorReporters(@Param("userId") Long userId);

    /** 历史查看允许停用人员，不影响填写入口的账号状态校验。 */
    String findReadEnglishName(@Param("userId") Long userId);

    String findEnglishName(@Param("userId") Long userId);

    Long lockReporter(@Param("userId") Long userId);

    List<LineOption> findLines();

    /** 只查询本人在时间段内有已保存日报的日期。 */
    List<LocalDate> findReportDates(
            @Param("userId") Long userId,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate);

    String findDepartmentName(@Param("userId") Long userId);

    /** 汇总当前投手在任务归属、代理线、平台和日期范围内填写的日报消耗。 */
    BigDecimal sumDailySpendForTask(
            @Param("userId") Long userId,
            @Param("projectId") Long projectId,
            @Param("agencyLineNames") List<String> agencyLineNames,
            @Param("platforms") List<String> platforms,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate);

    List<DeliveryReportRecord> findRecords(
            @Param("userId") Long userId, @Param("date") LocalDate date);

    void upsert(DeliveryReportRecord record);

    List<Attachment> findAttachments(@Param("reportId") Long reportId);

    List<Attachment> lockOwnedImages(@Param("userId") Long userId, @Param("ids") List<Long> ids);

    void clearAttachments(@Param("reportId") Long reportId);

    void insertAttachment(
            @Param("reportId") Long reportId,
            @Param("fileId") Long fileId,
            @Param("sortOrder") int sortOrder);
}
