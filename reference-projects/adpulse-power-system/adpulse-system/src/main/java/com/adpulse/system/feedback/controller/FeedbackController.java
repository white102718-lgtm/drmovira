package com.adpulse.system.feedback.controller;

import com.adpulse.system.auth.security.ClientIpResolver;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.feedback.dto.FeedbackRequests;
import com.adpulse.system.feedback.dto.FeedbackViews;
import com.adpulse.system.feedback.service.FeedbackService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 产品需求、问题与体验反馈接口。 */
@RestController
@RequestMapping("/feedbacks")
@Tag(name = "产品反馈", description = "反馈提交、诊断信息搜集和管理端处理")
public class FeedbackController {
    private final FeedbackService service;
    private final ClientIpResolver clientIpResolver;

    public FeedbackController(FeedbackService service, ClientIpResolver clientIpResolver) {
        this.service = service;
        this.clientIpResolver = clientIpResolver;
    }

    /** 当前登录用户提交反馈。账号和IP均由服务端身份与请求解析。 */
    @PostMapping
    @PreAuthorize("isAuthenticated()")
    @OperationAudit(
            module = "FEEDBACK",
            type = OperationType.CREATE,
            name = "提交产品反馈",
            targetType = "sys_feedback")
    public ApiResponse<FeedbackViews.Detail> create(
            @Valid @RequestBody FeedbackRequests.Create request,
            HttpServletRequest servletRequest) {
        return ApiResponse.success(
                service.create(
                        request,
                        clientIpResolver.resolve(servletRequest),
                        servletRequest.getHeader("User-Agent")));
    }

    /** 管理端分页查询反馈列表。 */
    @GetMapping
    @PreAuthorize("hasAuthority('system:feedback:manage')")
    public ApiResponse<PageResult<FeedbackViews.ListItem>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String category,
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.page(keyword, category, status, page, pageSize));
    }

    /** 管理端查询反馈状态汇总。 */
    @GetMapping("/summary")
    @PreAuthorize("hasAuthority('system:feedback:manage')")
    public ApiResponse<FeedbackViews.Summary> summary() {
        return ApiResponse.success(service.summary());
    }

    /** 管理端查询反馈完整信息。 */
    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('system:feedback:manage')")
    public ApiResponse<FeedbackViews.Detail> detail(@PathVariable Long id) {
        return ApiResponse.success(service.detail(id));
    }

    /** 管理端更新反馈状态和处理说明。 */
    @PutMapping("/{id}/status")
    @PreAuthorize("hasAuthority('system:feedback:manage')")
    @OperationAudit(
            module = "FEEDBACK",
            type = OperationType.UPDATE,
            name = "处理产品反馈",
            targetType = "sys_feedback",
            targetIdParameter = "id")
    public ApiResponse<FeedbackViews.Detail> updateStatus(
            @PathVariable Long id, @Valid @RequestBody FeedbackRequests.UpdateStatus request) {
        return ApiResponse.success(service.updateStatus(id, request));
    }
}
