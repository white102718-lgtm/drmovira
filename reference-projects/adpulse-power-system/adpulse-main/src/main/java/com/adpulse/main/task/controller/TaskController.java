package com.adpulse.main.task.controller;

import com.adpulse.main.task.dto.TaskRequests;
import com.adpulse.main.task.dto.TaskViews;
import com.adpulse.main.task.service.TaskDeliverySourceService;
import com.adpulse.main.task.service.TaskService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 任务中心创建、确认、交付和验收接口。 */
@RestController
@RequestMapping("/tasks")
public class TaskController {
    private final TaskService service;
    private final TaskDeliverySourceService deliverySourceService;

    public TaskController(TaskService service, TaskDeliverySourceService deliverySourceService) {
        this.service = service;
        this.deliverySourceService = deliverySourceService;
    }

    /** 按当前投手负责明细与日期范围同步交付数据。 */
    @GetMapping("/{taskId}/delivery-source")
    public ApiResponse<TaskViews.DeliverySource> deliverySource(
            @PathVariable Long taskId,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate startDate,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate endDate) {
        return ApiResponse.success(deliverySourceService.query(taskId, startDate, endDate));
    }

    /** 按当前用户获准的数据范围查询任务。 */
    @GetMapping
    public ApiResponse<TaskViews.Page<TaskViews.Task>> list(
            @RequestParam(required = false) String taskType,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "RELATED") String scope,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.list(taskType, status, keyword, scope, page, pageSize));
    }

    /** 按名称分页搜索投放代理线，仅返回稳定 ID 和名称。 */
    @GetMapping("/delivery-agency-lines")
    public ApiResponse<java.util.List<TaskViews.AgencyLineOption>> deliveryAgencyLines(
            @RequestParam(defaultValue = "") String keyword,
            @RequestParam(defaultValue = "1") int page) {
        return ApiResponse.success(service.deliveryAgencyLines(keyword, page));
    }

    /** 批量匹配导入文件中涉及的代理线名称。 */
    @PostMapping("/delivery-agency-lines/match")
    public ApiResponse<java.util.List<TaskViews.AgencyLineOption>> matchDeliveryAgencyLines(
            @Valid @RequestBody TaskRequests.AgencyLineMatch request) {
        return ApiResponse.success(service.matchDeliveryAgencyLines(request.names()));
    }

    /** 查询任务中心左侧导航数量，不加载列表详情。 */
    @GetMapping("/navigation-counts")
    public ApiResponse<TaskViews.NavigationCounts> navigationCounts() {
        return ApiResponse.success(service.navigationCounts());
    }

    /** 查询当前用户的任务草稿。 */
    @GetMapping("/drafts")
    public ApiResponse<java.util.List<TaskViews.Draft>> drafts() {
        return ApiResponse.success(service.listDrafts());
    }

    /** 查询当前用户关联任务的历史动态。 */
    @GetMapping("/activities")
    public ApiResponse<java.util.List<TaskViews.Activity>> activities(
            @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.success(service.listActivities(limit));
    }

    /** 查询当前用户的一项任务草稿。 */
    @GetMapping("/drafts/{draftId}")
    public ApiResponse<TaskViews.Draft> getDraft(@PathVariable Long draftId) {
        return ApiResponse.success(service.getDraft(draftId));
    }

    /** 新建任务草稿。 */
    @PostMapping("/drafts")
    public ApiResponse<TaskViews.Draft> createDraft(
            @Valid @RequestBody TaskRequests.DraftSave request) {
        return ApiResponse.success(service.createDraft(request));
    }

    /** 更新当前用户的一项任务草稿。 */
    @PutMapping("/drafts/{draftId}")
    public ApiResponse<TaskViews.Draft> updateDraft(
            @PathVariable Long draftId, @Valid @RequestBody TaskRequests.DraftSave request) {
        return ApiResponse.success(service.updateDraft(draftId, request));
    }

    /** 删除当前用户的一项任务草稿。 */
    @DeleteMapping("/drafts/{draftId}")
    public ApiResponse<Void> deleteDraft(@PathVariable Long draftId) {
        service.deleteDraft(draftId);
        return ApiResponse.success();
    }

    /** 查询任务详情。 */
    @GetMapping("/{taskId}")
    public ApiResponse<TaskViews.Detail> get(@PathVariable Long taskId) {
        return ApiResponse.success(service.get(taskId));
    }

    /** 查询来源投放任务关联的素材任务。 */
    @GetMapping("/{taskId}/material-tasks")
    public ApiResponse<TaskViews.Page<TaskViews.RelatedMaterialTask>> relatedMaterialTasks(
            @PathVariable Long taskId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.relatedMaterialTasks(taskId, page, pageSize));
    }

    /** 创建投放任务。 */
    @PostMapping("/delivery")
    public ApiResponse<TaskViews.Detail> createDelivery(
            @Valid @RequestBody TaskRequests.DeliveryCreate request) {
        return ApiResponse.success(service.createDelivery(request));
    }

    /** 创建素材任务。 */
    @PostMapping("/material")
    public ApiResponse<TaskViews.Detail> createMaterial(
            @Valid @RequestBody TaskRequests.MaterialCreate request) {
        return ApiResponse.success(service.createMaterial(request));
    }

    /** 旧分配入口已停用，返回明确提示，防止旧客户端绕过新增表单。 */
    @PostMapping("/{taskId}/delivery-allocations")
    public ApiResponse<TaskViews.Detail> assignDeliveryAllocations(
            @PathVariable Long taskId,
            @Valid @RequestBody TaskRequests.DeliveryAllocationAssign request) {
        return ApiResponse.success(service.assignDeliveryAllocations(taskId, request));
    }

    /** 查询当前用户关注的任务ID。 */
    @GetMapping("/follows")
    public ApiResponse<java.util.List<String>> follows() {
        return ApiResponse.success(service.listFollowedTaskIds());
    }

    /** 关注任务。 */
    @PostMapping("/{taskId}/follow")
    public ApiResponse<Void> follow(@PathVariable Long taskId) {
        service.follow(taskId);
        return ApiResponse.success();
    }

    /** 取消关注任务。 */
    @DeleteMapping("/{taskId}/follow")
    public ApiResponse<Void> unfollow(@PathVariable Long taskId) {
        service.unfollow(taskId);
        return ApiResponse.success();
    }

    /** 创建者分配任务负责人。 */
    @PostMapping("/{taskId}/assign")
    public ApiResponse<TaskViews.Detail> assign(
            @PathVariable Long taskId, @Valid @RequestBody TaskRequests.Assign request) {
        return ApiResponse.success(service.assign(taskId, request));
    }

    /** 负责人确认任务。 */
    @PostMapping("/{taskId}/confirm")
    public ApiResponse<TaskViews.Detail> confirm(@PathVariable Long taskId) {
        return ApiResponse.success(service.confirm(taskId));
    }

    /** 负责人驳回待确认任务。 */
    @PostMapping("/{taskId}/decline")
    public ApiResponse<TaskViews.Detail> decline(
            @PathVariable Long taskId, @Valid @RequestBody TaskRequests.Decline request) {
        return ApiResponse.success(service.decline(taskId, request));
    }

    /** 创建者撤回任务。 */
    @PostMapping("/{taskId}/withdraw")
    public ApiResponse<TaskViews.Detail> withdraw(
            @PathVariable Long taskId, @Valid @RequestBody TaskRequests.Withdraw request) {
        return ApiResponse.success(service.withdraw(taskId, request));
    }

    /** 创建者重新提交失败任务。 */
    @PostMapping("/{taskId}/resubmit")
    public ApiResponse<TaskViews.Detail> resubmit(@PathVariable Long taskId) {
        return ApiResponse.success(service.resubmit(taskId));
    }

    /** 创建者编辑后重新提交失败投放任务。 */
    @PutMapping("/{taskId}/delivery/resubmit")
    public ApiResponse<TaskViews.Detail> resubmitDelivery(
            @PathVariable Long taskId, @Valid @RequestBody TaskRequests.DeliveryCreate request) {
        return ApiResponse.success(service.resubmitDelivery(taskId, request));
    }

    /** 提交投放任务交付。 */
    @PostMapping("/{taskId}/delivery-submissions")
    public ApiResponse<TaskViews.Detail> submitDelivery(
            @PathVariable Long taskId,
            @Valid @RequestBody TaskRequests.DeliverySubmissionCreate request) {
        return ApiResponse.success(service.submitDelivery(taskId, request));
    }

    /** 提交素材任务交付。 */
    @PostMapping("/{taskId}/material-submissions")
    public ApiResponse<TaskViews.Detail> submitMaterial(
            @PathVariable Long taskId,
            @Valid @RequestBody TaskRequests.MaterialSubmissionCreate request) {
        return ApiResponse.success(service.submitMaterial(taskId, request));
    }

    /** 创建者验收通过交付。 */
    @PostMapping("/{taskId}/{type}-submissions/{submissionId}/accept")
    public ApiResponse<TaskViews.Detail> accept(
            @PathVariable Long taskId,
            @PathVariable String type,
            @PathVariable Long submissionId,
            @Valid @RequestBody TaskRequests.Review request) {
        return ApiResponse.success(service.accept(taskId, submissionId, type, request));
    }

    /** 创建者打回交付。 */
    @PostMapping("/{taskId}/{type}-submissions/{submissionId}/reject")
    public ApiResponse<TaskViews.Detail> reject(
            @PathVariable Long taskId,
            @PathVariable String type,
            @PathVariable Long submissionId,
            @Valid @RequestBody TaskRequests.Review request) {
        return ApiResponse.success(service.reject(taskId, submissionId, type, request));
    }
}
