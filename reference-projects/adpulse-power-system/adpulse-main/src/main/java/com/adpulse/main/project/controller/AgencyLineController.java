package com.adpulse.main.project.controller;

import com.adpulse.main.project.dto.ProjectRequests;
import com.adpulse.main.project.dto.ProjectViews;
import com.adpulse.main.project.service.ProjectService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 项目代理线接口。 */
@RestController
@RequestMapping("/project/agency-lines")
public class AgencyLineController {
    private final ProjectService service;

    public AgencyLineController(ProjectService service) {
        this.service = service;
    }

    /** 分页查询代理线。 */
    @GetMapping
    public ApiResponse<ProjectViews.Page<ProjectViews.AgencyLineDetail>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String lineName,
            @RequestParam(required = false) String platform,
            @RequestParam(required = false) Long projectId,
            @RequestParam(required = false) Long optimizerId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.listAgencyLines(
                        keyword, lineName, platform, projectId, optimizerId, page, pageSize));
    }

    /** 按名称搜索未绑定项目的轻量代理线选项。 */
    @GetMapping("/unbound-options")
    public ApiResponse<java.util.List<ProjectViews.AgencyLineOption>> unboundOptions(
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.listUnboundAgencyLineOptions(keyword));
    }

    /** 查询代理线。 */
    @GetMapping("/{id}")
    public ApiResponse<ProjectViews.AgencyLineDetail> get(@PathVariable Long id) {
        return ApiResponse.success(service.getAgencyLine(id));
    }

    /** 查询投放链接的全部历史版本。 */
    @GetMapping("/{id}/delivery-url-history")
    public ApiResponse<java.util.List<ProjectViews.AgencyLineDeliveryUrlHistory>>
            deliveryUrlHistory(@PathVariable Long id) {
        return ApiResponse.success(service.getAgencyLineDeliveryUrlHistory(id));
    }

    /** 创建代理线。 */
    @PostMapping
    public ApiResponse<ProjectViews.AgencyLineDetail> create(
            @RequestHeader(value = "Idempotency-Key", required = false) String requestId,
            @Valid @RequestBody ProjectRequests.AgencyLineCreate request) {
        return ApiResponse.success(
                service.createAgencyLine(request.agencyLine(), request.projectId(), requestId));
    }

    /** 修改代理线。 */
    @PutMapping("/{id}")
    public ApiResponse<ProjectViews.AgencyLineDetail> update(
            @PathVariable Long id, @Valid @RequestBody ProjectRequests.AgencyLineSave request) {
        return ApiResponse.success(service.updateAgencyLine(id, request));
    }

    /** 批量开启或关闭代理线业务状态，支持跨项目及未绑定的代理线。 */
    @PatchMapping("/status")
    public ApiResponse<Void> changeStatus(
            @Valid @RequestBody ProjectRequests.AgencyLineStatusChange request) {
        service.changeAgencyLineStatuses(request);
        return ApiResponse.success();
    }

    /** 仅更新单条代理线优化师，不覆盖其他配置。 */
    @PatchMapping("/{id}/optimizer")
    public ApiResponse<ProjectViews.AgencyLineDetail> changeOptimizer(
            @PathVariable Long id,
            @Valid @RequestBody ProjectRequests.AgencyLineOptimizerChange request) {
        return ApiResponse.success(service.changeAgencyLineOptimizer(id, request));
    }

    /** 删除代理线。 */
    @DeleteMapping("/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.deleteAgencyLine(id);
        return ApiResponse.success();
    }
}
