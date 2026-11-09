package com.adpulse.system.dailyreport.mapper;

import com.adpulse.system.dailyreport.model.DailyReportRule;
import com.adpulse.system.dailyreport.model.DailyReportSubmission;
import java.time.LocalDate;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface DailyReportMapper {
    List<DailyReportRule> findActiveRules();

    DailyReportRule findRuleByKey(@Param("ruleKey") String ruleKey);

    int insertRule(DailyReportRule rule);

    int updateRule(DailyReportRule rule);

    int deleteRule(@Param("ruleKey") String ruleKey, @Param("updatedBy") Long updatedBy);

    String findActiveUserName(@Param("userId") Long userId);

    List<String> findActiveFeishuOpenIds(@Param("userIds") List<Long> userIds);

    List<Long> findActiveUserIds(@Param("userIds") List<Long> userIds);

    List<Long> findActiveDepartmentIds(@Param("departmentIds") List<Long> departmentIds);

    List<Long> findActiveRoleIds(@Param("roleIds") List<Long> roleIds);

    List<Long> findActiveUserIdsByDepartments(@Param("departmentIds") List<Long> departmentIds);

    List<Long> findActiveUserIdsByRoles(@Param("roleIds") List<Long> roleIds);

    List<Long> findOwnedFileIds(@Param("fileIds") List<Long> fileIds, @Param("userId") Long userId);

    int insertSubmission(DailyReportSubmission submission);

    int updateSubmission(DailyReportSubmission submission);

    DailyReportSubmission findSubmissionById(@Param("id") Long id);

    int insertFileBindings(
            @Param("submissionId") Long submissionId,
            @Param("fileIds") List<Long> fileIds,
            @Param("userId") Long userId);

    int deactivateFileBindings(@Param("submissionId") Long submissionId);

    List<DailyReportSubmission> findSubmissions();

    int countSubmissions(
            @Param("ruleId") Long ruleId,
            @Param("userId") Long userId,
            @Param("periodKey") LocalDate periodKey);

    int insertReminderLog(
            @Param("ruleId") Long ruleId,
            @Param("userId") Long userId,
            @Param("reportDate") LocalDate reportDate,
            @Param("reminderTime") String reminderTime);
}
