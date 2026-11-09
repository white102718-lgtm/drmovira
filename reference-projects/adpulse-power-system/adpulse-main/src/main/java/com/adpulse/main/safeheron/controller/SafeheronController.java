package com.adpulse.main.safeheron.controller;

import com.adpulse.main.safeheron.dto.SafeheronRequests.ApproverSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RecordQuery;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleQuery;
import com.adpulse.main.safeheron.dto.SafeheronRequests.RuleSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.StatusSave;
import com.adpulse.main.safeheron.dto.SafeheronRequests.TeamCreate;
import com.adpulse.main.safeheron.dto.SafeheronViews;
import com.adpulse.main.safeheron.service.SafeheronService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Safeheron归集规则、审批人与执行记录接口。 */
@RestController
@RequestMapping("/safeheron")
public class SafeheronController {
    private static final MediaType XLSX =
            MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    private final SafeheronService service;

    public SafeheronController(SafeheronService service) {
        this.service = service;
    }

    /** 分页查询归集规则。 */
    @GetMapping("/rules")
    public ApiResponse<SafeheronViews.Page<SafeheronViews.Rule>> rules(RuleQuery query) {
        return ApiResponse.success(service.listRules(query));
    }

    /** 创建归集规则。 */
    @PostMapping("/rules")
    public ApiResponse<SafeheronViews.Rule> createRule(@Valid @RequestBody RuleSave request) {
        return ApiResponse.success(service.createRule(request));
    }

    /** 更新归集规则。 */
    @PutMapping("/rules/{id}")
    public ApiResponse<SafeheronViews.Rule> updateRule(
            @PathVariable Long id, @Valid @RequestBody RuleSave request) {
        return ApiResponse.success(service.updateRule(id, request));
    }

    /** 启用或停用归集规则。 */
    @PatchMapping("/rules/{id}/status")
    public ApiResponse<Void> updateRuleStatus(
            @PathVariable Long id, @Valid @RequestBody StatusSave request) {
        service.updateRuleStatus(id, request.status());
        return ApiResponse.success();
    }

    /** 删除归集规则。 */
    @DeleteMapping("/rules/{id}")
    public ApiResponse<Void> deleteRule(@PathVariable Long id) {
        service.deleteRule(id);
        return ApiResponse.success();
    }

    /** 查询归集目标钱包。 */
    @GetMapping("/wallets")
    public ApiResponse<List<SafeheronViews.Wallet>> wallets() {
        return ApiResponse.success(service.listWallets());
    }

    /** 查询钱包支持币种。 */
    @GetMapping("/wallets/{accountKey}/coins")
    public ApiResponse<List<SafeheronViews.Coin>> walletCoins(@PathVariable String accountKey) {
        return ApiResponse.success(service.listWalletCoins(accountKey));
    }

    /** 查询团队审批配置。 */
    @GetMapping("/teams")
    public ApiResponse<List<SafeheronViews.Team>> teams() {
        return ApiResponse.success(service.listTeams());
    }

    /** 新增Safeheron团队及API凭证，响应不包含任何敏感字段。 */
    @PostMapping("/teams")
    public ApiResponse<SafeheronViews.Team> createTeam(@Valid @RequestBody TeamCreate request) {
        return ApiResponse.success(service.createTeam(request));
    }

    /** 批量更新团队审批人。 */
    @PutMapping("/teams/approvers")
    public ApiResponse<Void> updateApprovers(@Valid @RequestBody List<ApproverSave> requests) {
        service.updateApprovers(requests);
        return ApiResponse.success();
    }

    /** 查询可选审批用户。 */
    @GetMapping("/users")
    public ApiResponse<List<SafeheronViews.User>> users() {
        return ApiResponse.success(service.listUsers());
    }

    /** 查询有效部门树。 */
    @GetMapping("/departments")
    public ApiResponse<List<SafeheronViews.Department>> departments() {
        return ApiResponse.success(service.departmentTree());
    }

    /** 分页查询归集记录。 */
    @GetMapping("/records")
    public ApiResponse<SafeheronViews.Page<SafeheronViews.CollectionRecord>> records(
            RecordQuery query) {
        return ApiResponse.success(service.listRecords(query));
    }

    /** 查询归集记录统计。 */
    @GetMapping("/records/statistics")
    public ApiResponse<SafeheronViews.RecordStatistics> recordStatistics(RecordQuery query) {
        return ApiResponse.success(service.recordStatistics(query));
    }

    /** 导出归集记录。 */
    @PostMapping("/records/export")
    public ResponseEntity<byte[]> exportRecords(RecordQuery query) {
        byte[] content = service.exportRecords(query);
        ContentDisposition disposition =
                ContentDisposition.attachment()
                        .filename("Safeheron归集记录.xlsx", StandardCharsets.UTF_8)
                        .build();
        return ResponseEntity.ok()
                .contentType(XLSX)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .contentLength(content.length)
                .body(content);
    }
}
