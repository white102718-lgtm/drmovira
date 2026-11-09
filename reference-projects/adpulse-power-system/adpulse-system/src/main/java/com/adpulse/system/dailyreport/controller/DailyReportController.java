package com.adpulse.system.dailyreport.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.dailyreport.service.DailyReportService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(name = "日报", description = "日报规则、提交记录、附件与定时提醒")
public class DailyReportController {
    private final DailyReportService service;

    public DailyReportController(DailyReportService service) {
        this.service = service;
    }

    @GetMapping("/daily-report-rules")
    @PreAuthorize("hasAuthority('system:daily-report:manage')")
    public ApiResponse<List<JsonNode>> listManagedRules() {
        return ApiResponse.success(service.listManagedRules());
    }

    @PutMapping("/daily-report-rules/{ruleKey}")
    @PreAuthorize("hasAuthority('system:daily-report:manage')")
    @OperationAudit(
            module = "DAILY_REPORT",
            type = OperationType.UPDATE,
            name = "保存日报规则",
            targetType = "sys_daily_report_rule",
            targetIdParameter = "ruleKey")
    public ApiResponse<JsonNode> saveRule(
            @PathVariable String ruleKey, @RequestBody JsonNode payload) {
        return ApiResponse.success(service.saveRule(ruleKey, payload));
    }

    @DeleteMapping("/daily-report-rules/{ruleKey}")
    @PreAuthorize("hasAuthority('system:daily-report:manage')")
    @OperationAudit(
            module = "DAILY_REPORT",
            type = OperationType.DELETE,
            name = "删除日报规则",
            targetType = "sys_daily_report_rule",
            targetIdParameter = "ruleKey")
    public ApiResponse<Void> deleteRule(@PathVariable String ruleKey) {
        service.deleteRule(ruleKey);
        return ApiResponse.success();
    }

    @GetMapping("/daily-reports/available-rules")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<JsonNode>> listAvailableRules() {
        return ApiResponse.success(service.listAvailableRules());
    }

    /**
     * Returns every active rule that the current user may see, together with whether it is
     * writable.
     */
    @GetMapping("/daily-reports/visible-rules")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<JsonNode>> listVisibleRules() {
        return ApiResponse.success(service.listVisibleRules());
    }

    @GetMapping("/daily-reports")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<JsonNode>> listSubmissions() {
        return ApiResponse.success(service.listSubmissions());
    }

    @PostMapping("/daily-reports")
    @PreAuthorize("isAuthenticated()")
    @OperationAudit(
            module = "DAILY_REPORT",
            type = OperationType.CREATE,
            name = "提交日报",
            targetType = "sys_daily_report_submission")
    public ApiResponse<JsonNode> submit(@RequestBody JsonNode payload) {
        return ApiResponse.success(service.submit(payload));
    }

    /** 日报重新提交仅允许原提交人修改同一条记录。 */
    @PutMapping("/daily-reports/{submissionId}")
    @PreAuthorize("isAuthenticated()")
    @OperationAudit(
            module = "DAILY_REPORT",
            type = OperationType.UPDATE,
            name = "重新提交日报",
            targetType = "sys_daily_report_submission",
            targetIdParameter = "submissionId")
    public ApiResponse<JsonNode> resubmit(
            @PathVariable String submissionId, @RequestBody JsonNode payload) {
        return ApiResponse.success(service.resubmit(submissionId, payload));
    }

    /** 兼容旧前端的通知调用；提交接口已在同一事务内投递站内消息。 */
    @PostMapping("/daily-reports/notifications")
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<Void> notifySubmitted() {
        return ApiResponse.success();
    }
}
