package com.adpulse.main.project.controller;

import com.adpulse.main.project.dto.ProjectRequests;
import com.adpulse.main.project.dto.ProjectViews;
import com.adpulse.main.project.service.ProjectService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 项目管理接口。 */
@RestController
@RequestMapping("/project/projects")
public class ProjectController {
    private final ProjectService service;

    public ProjectController(ProjectService service) {
        this.service = service;
    }

    /** 分页查询项目。 */
    @GetMapping
    public ApiResponse<ProjectViews.Page<ProjectViews.ProjectDetail>> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String platform,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.listProjects(keyword, status, platform, page, pageSize));
    }

    /** 查询全部项目的轻量下拉选项，不应用项目列表数据范围，仅返回项目ID和名称。 */
    @GetMapping("/options")
    public ApiResponse<List<ProjectViews.ProjectSearchOption>> options(
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.searchAllProjectOptions(keyword));
    }

    /** 按当前用户项目数据范围查询轻量下拉选项，仅返回项目ID和名称。 */
    @GetMapping("/options/scoped")
    public ApiResponse<List<ProjectViews.ProjectSearchOption>> scopedOptions(
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.searchScopedProjectOptions(keyword));
    }

    /** 查询项目关联代理线的轻量投放链接选项。 */
    @GetMapping("/{id}/agency-line-options")
    public ApiResponse<List<ProjectViews.ProjectAgencyLineDeliveryOption>> agencyLineOptions(
            @PathVariable Long id) {
        return ApiResponse.success(service.listProjectAgencyLineDeliveryOptions(id));
    }

    /** 独立查询项目列表和代理线列表的页签总数。 */
    @GetMapping("/tab-counts")
    public ApiResponse<ProjectViews.TabCounts> tabCounts() {
        return ApiResponse.success(service.getTabCounts());
    }

    /** 查询项目详情。 */
    @GetMapping("/{id}")
    public ApiResponse<ProjectViews.ProjectDetail> get(@PathVariable Long id) {
        return ApiResponse.success(service.getProject(id));
    }

    /** 查询项目页面统计和轻量项目选项。 */
    @GetMapping("/context")
    public ApiResponse<ProjectViews.ProjectContext> context() {
        return ApiResponse.success(service.getProjectContext());
    }

    /** 查询投放地区与国家级联选项。 */
    @GetMapping("/region-options")
    public ApiResponse<List<ProjectViews.RegionOption>> regionOptions() {
        return ApiResponse.success(service.listRegionOptions());
    }

    /** 创建项目。 */
    @PostMapping
    public ApiResponse<ProjectViews.ProjectDetail> create(
            @Valid @RequestBody ProjectRequests.ProjectSave request) {
        return ApiResponse.success(service.createProject(request));
    }

    /** 按当前字典配置为已有项目幂等创建或同步钱包。 */
    @PostMapping("/{id}/wallet")
    public ApiResponse<ProjectViews.ProjectWallet> createWallet(@PathVariable Long id) {
        return ApiResponse.success(service.createProjectWallet(id));
    }

    /** 修改项目。 */
    @PutMapping("/{id}")
    public ApiResponse<ProjectViews.ProjectDetail> update(
            @PathVariable Long id, @Valid @RequestBody ProjectRequests.ProjectSave request) {
        return ApiResponse.success(service.updateProject(id, request));
    }

    /** 增量绑定或解绑代理线。 */
    @PatchMapping("/{id}/agency-line-bindings")
    public ApiResponse<ProjectViews.ProjectDetail> patchAgencyLines(
            @PathVariable Long id, @Valid @RequestBody ProjectRequests.AgencyLinePatch request) {
        return ApiResponse.success(service.patchAgencyLines(id, request));
    }

    /** 覆盖项目当前代理线绑定。 */
    @PutMapping("/{id}/agency-lines")
    public ApiResponse<ProjectViews.ProjectDetail> replaceAgencyLines(
            @PathVariable Long id, @Valid @RequestBody ProjectRequests.AgencyLineReplace request) {
        return ApiResponse.success(service.replaceAgencyLines(id, request.agencyLineIds()));
    }

    /** 查询项目经营概览兼容投影。 */
    @GetMapping("/{id}/operating-overview")
    public ApiResponse<ProjectViews.OperatingOverview> operatingOverview(@PathVariable Long id) {
        return ApiResponse.success(service.operatingOverview(id));
    }

    /** 分页查询项目内已完成的投放和素材任务摘要。 */
    @GetMapping("/{id}/completed-tasks")
    public ApiResponse<ProjectViews.Page<ProjectViews.CompletedTask>> completedTasks(
            @PathVariable Long id,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int pageSize) {
        return ApiResponse.success(service.completedTasks(id, page, pageSize));
    }

    /** 原子批量修改代理线业务状态，不触发媒体广告操作。 */
    @PatchMapping("/{id}/agency-line-status")
    public ApiResponse<Void> changeAgencyLineStatus(
            @PathVariable Long id,
            @Valid @RequestBody ProjectRequests.AgencyLineStatusChange request) {
        service.changeAgencyLineStatus(id, request);
        return ApiResponse.success();
    }
}
