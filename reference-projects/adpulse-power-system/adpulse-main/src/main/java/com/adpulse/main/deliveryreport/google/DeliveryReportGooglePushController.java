package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushDtos.*;
import com.adpulse.main.google.dto.GoogleDtos.DriveFile;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** 投放日报Google模板、预览、推送和重试接口。 */
@RestController
@RequestMapping("/delivery-reports/google-push")
@PreAuthorize("hasAuthority('workbench:daily:report:push')")
public class DeliveryReportGooglePushController {
    private final DeliveryReportGooglePushService service;

    public DeliveryReportGooglePushController(DeliveryReportGooglePushService service) {
        this.service = service;
    }

    /** 查询模板可映射的系统字段。 */
    @GetMapping("/fields")
    public ApiResponse<List<FieldDefinition>> fields() {
        return ApiResponse.success(service.fields());
    }

    /** 查询日报推送使用的服务账户邮箱。 */
    @GetMapping("/service-account")
    public ApiResponse<ServiceAccountInfo> serviceAccount() {
        return ApiResponse.success(service.serviceAccount());
    }

    /** 查询已共享给日报服务账户的Google Sheets文件。 */
    @GetMapping("/files")
    public ApiResponse<List<DriveFile>> files(
            @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.files(keyword));
    }

    /** 查询服务账户可访问Spreadsheet中的页签。 */
    @GetMapping("/sheets")
    public ApiResponse<List<SheetTab>> sheets(@RequestParam String fileId) {
        return ApiResponse.success(service.sheets(fileId));
    }

    /** 根据项目日报链接自动匹配服务账户可访问的表格和页签。 */
    @GetMapping("/project-target")
    public ApiResponse<ProjectTarget> projectTarget(@RequestParam Long projectId) {
        return ApiResponse.success(service.projectTarget(projectId));
    }

    /** 查询目标页签指定行的表头。 */
    @GetMapping("/columns")
    public ApiResponse<List<String>> columns(
            @RequestParam String fileId,
            @RequestParam String sheetName,
            @RequestParam(defaultValue = "1") Integer headerRow) {
        return ApiResponse.success(service.columns(fileId, sheetName, headerRow));
    }

    /** 查询全部项目日报模板。 */
    @GetMapping("/templates")
    public ApiResponse<List<TemplateView>> templates() {
        return ApiResponse.success(service.templates());
    }

    /** 创建项目唯一模板。 */
    @PostMapping("/templates")
    public ApiResponse<String> createTemplate(@Valid @RequestBody TemplateSave request) {
        return ApiResponse.success(service.createTemplate(request));
    }

    /** 更新项目日报模板。 */
    @PutMapping("/templates/{id}")
    public ApiResponse<Void> updateTemplate(
            @PathVariable Long id, @Valid @RequestBody TemplateSave request) {
        service.updateTemplate(id, request);
        return ApiResponse.success();
    }

    /** 软删除项目日报模板。 */
    @DeleteMapping("/templates/{id}")
    public ApiResponse<Void> deleteTemplate(@PathVariable Long id) {
        service.deleteTemplate(id);
        return ApiResponse.success();
    }

    /** 校验所选日报并按项目返回Google写入预览。 */
    @PostMapping("/preview")
    public ApiResponse<Preview> preview(@Valid @RequestBody ReportSelection request) {
        return ApiResponse.success(service.preview(request));
    }

    /** 固化推送快照并创建后台批次。 */
    @PostMapping("/batches")
    public ApiResponse<PushBatchView> createBatch(@Valid @RequestBody ReportSelection request) {
        return ApiResponse.success(service.createBatch(request));
    }

    /** 查询当前用户最近发起的推送批次。 */
    @GetMapping("/batches")
    public ApiResponse<List<PushBatchView>> recentBatches() {
        return ApiResponse.success(service.recentBatches());
    }

    /** 查询当前用户发起的推送批次。 */
    @GetMapping("/batches/{id}")
    public ApiResponse<PushBatchView> batch(@PathVariable Long id) {
        return ApiResponse.success(service.batch(id));
    }

    /** 重试失败或部分失败的推送批次。 */
    @PostMapping("/batches/{id}/retry")
    public ApiResponse<PushBatchView> retry(@PathVariable Long id) {
        return ApiResponse.success(service.retry(id));
    }
}
