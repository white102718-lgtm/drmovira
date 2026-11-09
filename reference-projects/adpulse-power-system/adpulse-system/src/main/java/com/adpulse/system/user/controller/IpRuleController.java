package com.adpulse.system.user.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.adpulse.system.user.dto.IpRuleSaveRequest;
import com.adpulse.system.user.model.IpRule;
import com.adpulse.system.user.service.IpRuleService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 通用IP白名单管理接口。 */
@RestController
@RequestMapping("/ip-rules/global")
@Tag(name = "IP规则管理", description = "通用IP白名单维护")
@PreAuthorize("hasAuthority('system:user:list')")
public class IpRuleController {

    private final IpRuleService service;

    public IpRuleController(IpRuleService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<List<IpRule>> list() {
        return ApiResponse.success(service.listGlobalRules());
    }

    @PostMapping
    @OperationAudit(
            module = "IP_RULE",
            type = OperationType.CREATE,
            name = "新增通用IP规则",
            targetType = "sys_ip_rule")
    public ApiResponse<IpRule> create(@Valid @RequestBody IpRuleSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @OperationAudit(
            module = "IP_RULE",
            type = OperationType.UPDATE,
            name = "修改通用IP规则",
            targetType = "sys_ip_rule",
            targetIdParameter = "id")
    public ApiResponse<IpRule> update(
            @PathVariable Long id, @Valid @RequestBody IpRuleSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @OperationAudit(
            module = "IP_RULE",
            type = OperationType.DELETE,
            name = "删除通用IP规则",
            targetType = "sys_ip_rule",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
