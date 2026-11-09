package com.adpulse.system.dailyreport.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.dailyreport.mapper.DailyReportMapper;
import com.adpulse.system.dailyreport.model.DailyReportRule;
import com.adpulse.system.dailyreport.model.DailyReportSubmission;
import com.adpulse.system.notification.service.SiteNotificationPublisher;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

class DailyReportServiceTest {
    private final DailyReportMapper mapper = mock(DailyReportMapper.class);
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final FeishuDailyReportNotifier feishuNotifier = mock(FeishuDailyReportNotifier.class);
    private final SiteNotificationPublisher siteNotificationPublisher =
            mock(SiteNotificationPublisher.class);
    private final DailyReportService service =
            new DailyReportService(mapper, objectMapper, feishuNotifier, siteNotificationPublisher);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void rejectsSubmissionFromUserOutsideWriterScope() {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("daily-team");
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"团队日报","period":"每天","fields":[],
                 "personnel":{"writers":[{"id":"user:2"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1],"startTime":"00:00","deadlineTime":"18:00","reminderTime":"16:00"}}
                """);
        when(mapper.findRuleByKey("daily-team")).thenReturn(rule);

        assertThatThrownBy(
                        () ->
                                service.submit(
                                        objectMapper.readTree(
                                                "{\"ruleId\":\"daily-team\",\"fields\":{}}")))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.ACCESS_DENIED);
    }

    @Test
    void returnsPersistedSubmissionAfterInsert() throws Exception {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("daily-team");
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","period":"\u6bcf\u5929","fields":[],
                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                """);
        when(mapper.findRuleByKey("daily-team")).thenReturn(rule);
        when(mapper.findActiveUserName(1L)).thenReturn("tester");
        doAnswer(
                        invocation -> {
                            invocation.getArgument(0, DailyReportSubmission.class).setId(99L);
                            return 1;
                        })
                .when(mapper)
                .insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
        DailyReportSubmission persisted = new DailyReportSubmission();
        persisted.setId(99L);
        persisted.setSubmittedById(1L);
        persisted.setSubmittedByName("tester");
        persisted.setCreatedAt(LocalDateTime.of(2026, 8, 31, 12, 0));
        persisted.setFieldValuesJson("{}");
        persisted.setAttachmentsJson("{}");
        persisted.setRuleSnapshotJson("{\"id\":\"daily-team\"}");
        when(mapper.findSubmissionById(99L)).thenReturn(persisted);

        var result =
                service.submit(objectMapper.readTree("{\"ruleId\":\"daily-team\",\"fields\":{}}"));

        assertThat(result.path("id").asText()).isEqualTo("99");
        assertThat(result.path("createdAt").asText()).isEqualTo("2026-08-31T12:00");
        verify(mapper).findSubmissionById(99L);
    }

    @Test
    void usesSelectedSettlementMonthAsMaterialDesignerReportingPeriod() throws Exception {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("material-designer-daily-report");
        rule.setConfigJson(
                """
                {"id":"material-designer-daily-report","name":"素材师日报","period":"每天","fields":[],
                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                """);
        when(mapper.findRuleByKey("material-designer-daily-report")).thenReturn(rule);
        when(mapper.findActiveUserName(1L)).thenReturn("素材师甲");
        doAnswer(
                        invocation -> {
                            invocation.getArgument(0, DailyReportSubmission.class).setId(99L);
                            return 1;
                        })
                .when(mapper)
                .insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
        DailyReportSubmission persisted = new DailyReportSubmission();
        persisted.setId(99L);
        persisted.setSubmittedById(1L);
        persisted.setSubmittedByName("素材师甲");
        persisted.setCreatedAt(LocalDateTime.of(2026, 9, 8, 12, 0));
        persisted.setFieldValuesJson("{}");
        persisted.setAttachmentsJson("{}");
        persisted.setRuleSnapshotJson("{\"id\":\"material-designer-daily-report\"}");
        when(mapper.findSubmissionById(99L)).thenReturn(persisted);

        service.submit(
                objectMapper.readTree(
                        """
                        {"ruleId":"material-designer-daily-report","fields":{
                          "settlementMonth":"2026-07","commissionRate":"10",
                          "pitcherIds":"101","projectIds":"201","taskLineIds":"301"
                        }}
                        """));

        ArgumentCaptor<DailyReportSubmission> captor =
                ArgumentCaptor.forClass(DailyReportSubmission.class);
        verify(mapper).insertSubmission(captor.capture());
        assertThat(captor.getValue().getReportDate()).isEqualTo(LocalDate.of(2026, 7, 1));
        assertThat(captor.getValue().getPeriodKey()).isEqualTo(LocalDate.of(2026, 7, 1));
    }

    @Test
    void rejectsInvalidMaterialDesignerSettlementMonth() throws Exception {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("material-designer-daily-report");
        rule.setConfigJson(
                """
                {"id":"material-designer-daily-report","name":"素材师月报","period":"每月","fields":[],
                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                """);
        when(mapper.findRuleByKey("material-designer-daily-report")).thenReturn(rule);
        when(mapper.findActiveUserName(1L)).thenReturn("素材师甲");

        assertThatThrownBy(
                        () ->
                                service.submit(
                                        objectMapper.readTree(
                                                """
                                                {"ruleId":"material-designer-daily-report","fields":{
                                                  "settlementMonth":"2026-13","commissionRate":"10",
                                                  "pitcherIds":"101","projectIds":"201","taskLineIds":"301"
                                                }}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);
        verify(mapper, never())
                .insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
    }

    @Test
    void sendsFeishuNotificationForLegacyRuleWithoutChannelConfig() throws Exception {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("daily-team");
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","period":"每天","fields":[],
                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:2"}],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                """);
        when(mapper.findRuleByKey("daily-team")).thenReturn(rule);
        when(mapper.findActiveUserName(1L)).thenReturn("tester");
        doAnswer(
                        invocation -> {
                            invocation.getArgument(0, DailyReportSubmission.class).setId(99L);
                            return 1;
                        })
                .when(mapper)
                .insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
        DailyReportSubmission persisted = new DailyReportSubmission();
        persisted.setId(99L);
        persisted.setSubmittedById(1L);
        persisted.setSubmittedByName("tester");
        persisted.setCreatedAt(LocalDateTime.of(2026, 8, 31, 12, 0));
        persisted.setFieldValuesJson("{}");
        persisted.setAttachmentsJson("{}");
        persisted.setRuleSnapshotJson("{\"id\":\"daily-team\"}");
        when(mapper.findSubmissionById(99L)).thenReturn(persisted);

        service.submit(objectMapper.readTree("{\"ruleId\":\"daily-team\",\"fields\":{}}"));

        verify(feishuNotifier)
                .notifyRecipients(
                        org.mockito.ArgumentMatchers.eq(List.of(2L)),
                        org.mockito.ArgumentMatchers.contains("tester 已提交「report」"));
    }

    @Test
    void rejectsSecondSubmissionInTheSameReportingPeriod() throws Exception {
        authenticate(1L);
        DailyReportRule rule = new DailyReportRule();
        rule.setId(12L);
        rule.setRuleKey("daily-team");
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","period":"每天","fields":[],
                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                """);
        when(mapper.findRuleByKey("daily-team")).thenReturn(rule);
        when(mapper.findActiveUserName(1L)).thenReturn("tester");
        when(mapper.insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class)))
                .thenThrow(new DuplicateKeyException("duplicate reporting period"));

        assertThatThrownBy(
                        () ->
                                service.submit(
                                        objectMapper.readTree(
                                                "{\"ruleId\":\"daily-team\",\"fields\":{}}")))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.BUSINESS_CONFLICT);
    }

    @Test
    void allowsOnlySubmitterToResubmitTheirDailyReport() throws Exception {
        authenticate(2L);
        DailyReportSubmission submission = new DailyReportSubmission();
        submission.setId(10L);
        submission.setSubmittedById(1L);
        when(mapper.findSubmissionById(10L)).thenReturn(submission);

        assertThatThrownBy(() -> service.resubmit("10", objectMapper.readTree("{\"fields\":{}}")))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.ACCESS_DENIED);
        verify(mapper, never())
                .updateSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
    }

    @Test
    void resubmitsTheOriginalRecordWithoutCreatingAnotherDailyReport() throws Exception {
        authenticate(1L);
        DailyReportSubmission submission = new DailyReportSubmission();
        submission.setId(10L);
        submission.setSubmittedById(1L);
        submission.setSubmittedByName("tester");
        submission.setCreatedAt(LocalDateTime.of(2026, 8, 31, 12, 0));
        submission.setFieldValuesJson("{}");
        submission.setAttachmentsJson("{}");
        submission.setRuleSnapshotJson(
                """
                {"id":"daily-team","name":"report","fields":[],
                 "personnel":{"reporters":[],"cc":[]}}
                """);
        when(mapper.findSubmissionById(10L)).thenReturn(submission);
        when(mapper.updateSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class)))
                .thenReturn(1);

        var result = service.resubmit("10", objectMapper.readTree("{\"fields\":{}}"));

        assertThat(result.path("id").asText()).isEqualTo("10");
        verify(mapper).updateSubmission(submission);
        verify(mapper).deactivateFileBindings(10L);
        verify(mapper, never())
                .insertSubmission(org.mockito.ArgumentMatchers.any(DailyReportSubmission.class));
    }

    @Test
    void rejectsRuleWithNonIanaTimezone() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));
        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree(
                                                """
                                                {"name":"团队日报","period":"每天","fields":[],
                                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[],"viewerScope":"custom"},
                                                 "schedule":{"timezone":"中国标准时间","submissionDays":[1]}}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);
    }

    @Test
    void requiresWritersAndReportersWhenSavingRule() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree(
                                                """
                                                {"name":"report","period":"每天","fields":[],
                                                 "personnel":{"writers":[],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[],"viewerScope":"custom"},
                                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);

        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree(
                                                """
                                                {"name":"report","period":"每天","fields":[],
                                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);
    }

    @Test
    void acceptsRuleWithoutViewersWhenRequiredParticipantsConfigured() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        var saved =
                service.saveRule(
                        "daily-team",
                        objectMapper.readTree(
                                """
                                {"name":"report","period":"每天","fields":[],
                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                """));

        assertThat(saved.path("personnel").path("viewers")).isEmpty();
        verify(mapper).insertRule(org.mockito.ArgumentMatchers.any(DailyReportRule.class));
    }

    @Test
    void acceptsSystemDepartmentScope() throws Exception {
        authenticate(1L);
        when(mapper.findActiveDepartmentIds(List.of(6L))).thenReturn(List.of(6L));

        var saved =
                service.saveRule(
                        "daily-team",
                        objectMapper.readTree(
                                """
                                {"name":"report","period":"每天","fields":[],
                                 "personnel":{"writers":[{"id":"department:6"}],"reporters":[{"id":"department:6"}],"cc":[],"viewers":[{"id":"department:6"}],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                """));

        assertThat(saved.path("personnel").path("writers").get(0).path("id").asText())
                .isEqualTo("department:6");
        verify(mapper).insertRule(org.mockito.ArgumentMatchers.any(DailyReportRule.class));
    }

    @Test
    void rejectsLegacyDepartmentScope() throws Exception {
        authenticate(1L);

        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree(
                                                """
                                                {"name":"report","period":"每天","fields":[],
                                                 "personnel":{"writers":[{"id":"department:6a1fc25b8b6a3c3bb54f4852"}],"reporters":[],"cc":[],"viewers":[],"viewerScope":"custom"},
                                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);
    }

    @Test
    void acceptsSystemRoleScope() throws Exception {
        authenticate(1L);
        when(mapper.findActiveRoleIds(List.of(1L))).thenReturn(List.of(1L));

        var saved =
                service.saveRule(
                        "daily-team",
                        objectMapper.readTree(
                                """
                                {"name":"report","period":"每天","fields":[],
                                 "personnel":{"writers":[{"id":"role:1"}],"reporters":[{"id":"role:1"}],"cc":[],"viewers":[{"id":"role:1"}],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                """));

        assertThat(saved.path("personnel").path("writers").get(0).path("id").asText())
                .isEqualTo("role:1");
    }

    @Test
    void clearsWeekdaysForDailyRules() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        var saved =
                service.saveRule(
                        "daily-team",
                        objectMapper.readTree(
                                """
                                {"name":"report","period":"每天","fields":[],
                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[{"id":"user:1"}],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1,2,3]}}
                                """));

        assertThat(saved.path("schedule").path("submissionDays")).isEmpty();
    }

    @Test
    void acceptsMonthlySubmissionDay() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        var saved =
                service.saveRule(
                        "monthly-team",
                        objectMapper.readTree(
                                """
                                {"name":"report","period":"每月","fields":[],
                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[{"id":"user:1"}],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDayOfMonth":15,"submissionDays":[1]}}
                                """));

        assertThat(saved.path("schedule").path("submissionDayOfMonth").asInt()).isEqualTo(15);
        assertThat(saved.path("schedule").path("submissionDays")).isEmpty();
        assertThat(saved.path("schedule").path("deadlineTime").asText()).isEqualTo("23:00");
        assertThat(saved.path("schedule").path("reminderTime").asText()).isEqualTo("19:00");
    }

    @Test
    void rejectsLegacyAllViewerScope() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree(
                                                """
                                                {"name":"report","period":"每天","fields":[],
                                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[],"viewerScope":"all"},
                                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                                                """)))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.VALIDATION_ERROR);
    }

    @Test
    void rejectsUpdateByNonOwner() throws Exception {
        authenticate(2L);
        DailyReportRule existing = new DailyReportRule();
        existing.setCreatedBy(1L);
        when(mapper.findRuleByKey("daily-team")).thenReturn(existing);

        assertThatThrownBy(
                        () ->
                                service.saveRule(
                                        "daily-team",
                                        objectMapper.readTree("{\"name\":\"report\"}")))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.ACCESS_DENIED);
    }

    @Test
    void rejectsDeletingFixedDailyReportRule() {
        authenticate(1L);
        DailyReportRule fixedRule = new DailyReportRule();
        fixedRule.setCreatedBy(1L);
        when(mapper.findRuleByKey("delivery-daily-report")).thenReturn(fixedRule);

        assertThatThrownBy(() -> service.deleteRule("delivery-daily-report"))
                .isInstanceOf(BusinessException.class)
                .extracting(exception -> ((BusinessException) exception).getCode())
                .isEqualTo(ApiCode.BUSINESS_CONFLICT);

        verify(mapper, never()).deleteRule(anyString(), anyLong());
    }

    @Test
    void normalizesMaterialDesignerMonthlyReportAndRetainsPersonnelSettings() throws Exception {
        authenticate(1L);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        var saved =
                service.saveRule(
                        "material-designer-daily-report",
                        objectMapper.readTree(
                                """
                                {"name":"素材师日报","period":"每天","fields":[{"id":"legacy","label":"旧字段"}],
                                 "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[{"id":"user:1"}],"viewers":[{"id":"user:1"}],"viewerScope":"custom"},
                                 "schedule":{"timezone":"Asia/Shanghai","submissionDays":[]}}
                                """));

        assertThat(saved.path("fields")).isEmpty();
        assertThat(saved.path("name").asText()).isEqualTo("素材师月报");
        assertThat(saved.path("period").asText()).isEqualTo("每月");
        assertThat(saved.path("schedule").path("submissionDayOfMonth").asInt()).isEqualTo(1);
        assertThat(saved.path("personnel").path("reporters").get(0).path("id").asText())
                .isEqualTo("user:1");
        assertThat(saved.path("personnel").path("cc").get(0).path("id").asText())
                .isEqualTo("user:1");
    }

    @Test
    void listsOnlyRulesCreatedByCurrentUserForNonAdministrators() {
        authenticate(1L);
        DailyReportRule owned = new DailyReportRule();
        owned.setCreatedBy(1L);
        owned.setConfigJson("{}");
        DailyReportRule anotherUsersRule = new DailyReportRule();
        anotherUsersRule.setCreatedBy(2L);
        anotherUsersRule.setConfigJson("{}");
        when(mapper.findActiveRules()).thenReturn(List.of(owned, anotherUsersRule));

        assertThat(service.listManagedRules()).hasSize(1);
    }

    @Test
    void exposesRulesToCcUsersButDoesNotMakeThemWritable() {
        authenticate(2L);
        DailyReportRule rule = new DailyReportRule();
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","personnel":{
                  "writers":[{"id":"user:1"}],"reporters":[],"cc":[{"id":"user:2"}],"viewers":[]}}
                """);
        when(mapper.findActiveRules()).thenReturn(List.of(rule));

        assertThat(service.listAvailableRules()).isEmpty();
        var visible = service.listVisibleRules();

        assertThat(visible).hasSize(1);
        assertThat(visible.get(0).path("id").asText()).isEqualTo("daily-team");
        assertThat(visible.get(0).path("canWrite").asBoolean()).isFalse();
    }

    @Test
    void exposesRulesToReportersButDoesNotMakeThemWritable() {
        authenticate(2L);
        DailyReportRule rule = new DailyReportRule();
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","personnel":{
                  "writers":[{"id":"user:1"}],"reporters":[{"id":"user:2"}],"cc":[],"viewers":[]}}
                """);
        when(mapper.findActiveRules()).thenReturn(List.of(rule));

        assertThat(service.listAvailableRules()).isEmpty();
        var visible = service.listVisibleRules();

        assertThat(visible).hasSize(1);
        assertThat(visible.get(0).path("id").asText()).isEqualTo("daily-team");
        assertThat(visible.get(0).path("canWrite").asBoolean()).isFalse();
    }

    @Test
    void exposesRulesToUsersSelectedByRole() {
        authenticate(2L);
        DailyReportRule rule = new DailyReportRule();
        rule.setConfigJson(
                """
                {"id":"daily-team","name":"report","personnel":{
                  "writers":[{"id":"user:1"}],"reporters":[],"cc":[{"id":"role:8"}],"viewers":[]}}
                """);
        when(mapper.findActiveRules()).thenReturn(List.of(rule));
        when(mapper.findActiveUserIdsByRoles(List.of(8L))).thenReturn(List.of(2L));

        var visible = service.listVisibleRules();

        assertThat(visible).hasSize(1);
        assertThat(visible.get(0).path("canWrite").asBoolean()).isFalse();
    }

    @Test
    void doesNotExposeRuleToSystemAdministratorOutsideConfiguredScopes() {
        authenticateAdministrator(2L);
        DailyReportRule rule = new DailyReportRule();
        rule.setRuleKey("material-designer-daily-report");
        rule.setConfigJson(
                """
                {"id":"material-designer-daily-report","name":"素材师日报","period":"每天",
                 "schedule":{"submissionDays":[]},"personnel":{
                  "writers":[{"id":"user:1"}],"reporters":[],"cc":[],"viewers":[]}}
                """);
        when(mapper.findActiveRules()).thenReturn(List.of(rule));

        assertThat(service.listAvailableRules()).isEmpty();
        assertThat(service.listVisibleRules()).isEmpty();
    }

    @Test
    void allowsCcUsersToSeeSubmittedReports() {
        authenticate(2L);
        DailyReportSubmission submission = new DailyReportSubmission();
        submission.setId(10L);
        submission.setSubmittedById(1L);
        submission.setSubmittedByName("writer");
        submission.setCreatedAt(LocalDateTime.of(2026, 8, 31, 12, 0));
        submission.setFieldValuesJson("{}");
        submission.setAttachmentsJson("{}");
        submission.setRuleSnapshotJson(
                """
                {"id":"daily-team","personnel":{"writers":[{"id":"user:1"}],
                 "reporters":[],"cc":[{"id":"user:2"}],"viewers":[]}}
                """);
        when(mapper.findSubmissions()).thenReturn(List.of(submission));

        var reports = service.listSubmissions();

        assertThat(reports).hasSize(1);
        assertThat(reports.get(0).path("authorId").asText()).isEqualTo("1");
    }

    @Test
    void allowsDepartmentScopedReportersToSeeSubmittedReports() {
        authenticate(2L);
        DailyReportSubmission submission = new DailyReportSubmission();
        submission.setId(10L);
        submission.setSubmittedById(1L);
        submission.setSubmittedByName("writer");
        submission.setCreatedAt(LocalDateTime.of(2026, 8, 31, 12, 0));
        submission.setFieldValuesJson("{}");
        submission.setAttachmentsJson("{}");
        submission.setRuleSnapshotJson(
                """
                {"id":"daily-team","personnel":{"writers":[{"id":"user:1"}],
                 "reporters":[{"id":"department:6"}],"cc":[],"viewers":[]}}
                """);
        when(mapper.findSubmissions()).thenReturn(List.of(submission));
        when(mapper.findActiveUserIdsByDepartments(List.of(6L))).thenReturn(List.of(2L));

        var reports = service.listSubmissions();

        assertThat(reports).hasSize(1);
        assertThat(reports.get(0).path("id").asText()).isEqualTo("10");
    }

    @Test
    void allowsSystemAdministratorToUpdateAnotherUsersRule() throws Exception {
        authenticateAdministrator(2L);
        DailyReportRule existing = new DailyReportRule();
        existing.setCreatedBy(1L);
        when(mapper.findRuleByKey("daily-team")).thenReturn(existing);
        when(mapper.findActiveUserIds(List.of(1L))).thenReturn(List.of(1L));

        service.saveRule(
                "daily-team",
                objectMapper.readTree(
                        """
                        {"name":"report","period":"每天","fields":[],
                         "personnel":{"writers":[{"id":"user:1"}],"reporters":[{"id":"user:1"}],"cc":[],"viewers":[{"id":"user:1"}],"viewerScope":"custom"},
                         "schedule":{"timezone":"Asia/Shanghai","submissionDays":[1]}}
                        """));

        verify(mapper).updateRule(org.mockito.ArgumentMatchers.any(DailyReportRule.class));
    }

    private void authenticate(long userId) {
        CurrentUser user = new CurrentUser(userId, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, user.getAuthorities()));
    }

    private void authenticateAdministrator(long userId) {
        CurrentUser user =
                new CurrentUser(
                        userId,
                        "session",
                        "系统管理员",
                        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, user.getAuthorities()));
    }
}
