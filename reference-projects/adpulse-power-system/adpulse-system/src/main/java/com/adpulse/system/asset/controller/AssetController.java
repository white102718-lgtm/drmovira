package com.adpulse.system.asset.controller;

import com.adpulse.system.asset.dto.AssetImportViews;
import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.model.ApprovalConfig;
import com.adpulse.system.asset.model.AssetApplication;
import com.adpulse.system.asset.model.MediaAsset;
import com.adpulse.system.asset.service.AssetService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 资产管理、申请、审批和个人资产接口。 */
@RestController
@RequestMapping("/asset-flow")
@Tag(name = "资产流程", description = "个号、BM、像素和TG的申请审批闭环")
public class AssetController {
    private final AssetService service;

    public AssetController(AssetService service) {
        this.service = service;
    }

    @GetMapping("/assets")
    public ApiResponse<List<MediaAsset>> assets(
            @RequestParam(required = false) String assetType,
            @RequestParam(required = false) String channelId,
            @RequestParam(required = false) String projectId) {
        return ApiResponse.success(
                service.assets(assetType, channelId == null ? projectId : channelId));
    }

    /** 资产管理页按筛选条件检索库存；旧列表接口继续为其他调用方保留全量契约。 */
    @PostMapping("/assets/search")
    public ApiResponse<AssetViews.AssetPage> searchAssets(
            @Valid @RequestBody AssetRequests.AssetSearch request) {
        return ApiResponse.success(service.searchAssets(request));
    }

    /** 按资产管理页当前筛选条件一次返回全部命中资产，供表格导出使用。 */
    @PostMapping("/assets/search-all")
    public ApiResponse<List<MediaAsset>> searchAllAssets(
            @Valid @RequestBody AssetRequests.AssetSearch request) {
        return ApiResponse.success(service.searchAllAssets(request));
    }

    /** 返回资产的脱敏生命周期、使用区间与原申请单关联。 */
    @GetMapping("/assets/{id}/lifecycle")
    public ApiResponse<AssetViews.AssetLifecycleDetail> lifecycle(@PathVariable Long id) {
        return ApiResponse.success(service.lifecycle(id));
    }

    @PostMapping("/assets")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.CREATE,
            name = "新增资产",
            targetType = "media_asset")
    public ApiResponse<MediaAsset> createAsset(
            @Valid @RequestBody AssetRequests.AssetSave request) {
        return ApiResponse.success(service.createAsset(request));
    }

    /** 上传资产 Excel 或 CSV；所有表头、字段和使用人校验均由服务端处理。 */
    @PostMapping(value = "/assets/import", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @OperationAudit(
            module = "ASSET",
            type = OperationType.CREATE,
            name = "批量导入资产",
            targetType = "media_asset")
    public ApiResponse<AssetImportViews.Result> importAssets(
            @RequestParam String subtype, @RequestPart("file") MultipartFile file)
            throws java.io.IOException {
        if (file.isEmpty()) {
            throw com.adpulse.system.common.exception.BusinessException.validation("请选择导入文件");
        }
        if (file.getSize() > 5L * 1024 * 1024) {
            throw com.adpulse.system.common.exception.BusinessException.validation("导入文件不能超过 5MB");
        }
        return ApiResponse.success(
                service.importAssets(file.getBytes(), subtype, file.getOriginalFilename()));
    }

    /** 仅查询当前登录用户创建的资产导入记录。 */
    @GetMapping("/assets/import-records")
    public ApiResponse<PageResult<AssetImportViews.History>> importHistory(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int pageSize) {
        return ApiResponse.success(service.importHistory(page, pageSize));
    }

    /** 仅允许下载当前登录用户自己的加密失败工作簿。 */
    @GetMapping("/assets/import-records/{id}/failed-file")
    public ApiResponse<AssetImportViews.FailedFile> failedImportFile(@PathVariable Long id) {
        return ApiResponse.success(service.failedImportFile(id));
    }

    @PutMapping("/assets/{id}")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "修改资产",
            targetType = "media_asset",
            targetIdParameter = "id")
    public ApiResponse<MediaAsset> updateAsset(
            @PathVariable Long id, @Valid @RequestBody AssetRequests.AssetSave request) {
        return ApiResponse.success(service.updateAsset(id, request));
    }

    /** 按显式字段白名单批量修改同一资产类型下的库存资料。 */
    @PatchMapping("/assets/batch")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "批量修改资产",
            targetType = "media_asset")
    public ApiResponse<List<MediaAsset>> batchUpdateAssets(
            @Valid @RequestBody AssetRequests.AssetBatchUpdate request) {
        return ApiResponse.success(service.batchUpdateAssets(request));
    }

    /** 电子表格打开时批量读取最新资产快照。 */
    @PostMapping("/assets/batch-query")
    public ApiResponse<List<MediaAsset>> batchQueryAssets(
            @Valid @RequestBody AssetRequests.AssetBatchQuery request) {
        return ApiResponse.success(service.batchQueryAssets(request));
    }

    /** 粘贴数据时按资产类型和业务唯一标识批量读取已有资产快照。 */
    @PostMapping("/assets/batch-query-by-identifiers")
    public ApiResponse<List<MediaAsset>> batchQueryAssetsByIdentifiers(
            @Valid @RequestBody AssetRequests.AssetIdentifierBatchQuery request) {
        return ApiResponse.success(service.batchQueryAssetsByIdentifiers(request));
    }

    /** 电子表格中的新增和逐行修改在同一事务内原子保存。 */
    @PostMapping("/assets/spreadsheet")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "电子表格批量编辑资产",
            targetType = "media_asset")
    public ApiResponse<AssetViews.AssetSpreadsheetSaveResult> spreadsheetSave(
            @Valid @RequestBody AssetRequests.AssetSpreadsheetSave request) {
        return ApiResponse.success(service.spreadsheetSave(request));
    }

    /** 仅允许为已分配的广告账户补充或调整实际使用人。 */
    @PutMapping("/assets/{id}/usage-user")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "指定广告账户使用人",
            targetType = "media_asset",
            targetIdParameter = "id")
    public ApiResponse<MediaAsset> updateUsageUser(
            @PathVariable Long id, @Valid @RequestBody AssetRequests.UsageUserSave request) {
        return ApiResponse.success(service.updateAdAccountUsageUser(id, request.usageUserId()));
    }

    @DeleteMapping("/assets/{id}")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.DELETE,
            name = "删除资产",
            targetType = "media_asset",
            targetIdParameter = "id")
    public ApiResponse<Void> deleteAsset(@PathVariable Long id) {
        service.deleteAsset(id);
        return ApiResponse.success();
    }

    @GetMapping("/assets/mine")
    public ApiResponse<List<MediaAsset>> myAssets() {
        return ApiResponse.success(service.myAssets());
    }

    @GetMapping("/approval-configs")
    public ApiResponse<List<ApprovalConfig>> configs() {
        return ApiResponse.success(service.configs());
    }

    @PutMapping("/approval-configs")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "配置资产审批人",
            targetType = "media_approval_config")
    public ApiResponse<ApprovalConfig> saveConfig(
            @Valid @RequestBody AssetRequests.ApprovalConfigSave request) {
        return ApiResponse.success(service.saveConfig(request));
    }

    @PostMapping("/applications")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.CREATE,
            name = "提交资产申请",
            targetType = "media_asset_application")
    public ApiResponse<AssetApplication> apply(
            @Valid @RequestBody AssetRequests.ApplicationCreate request) {
        return ApiResponse.success(service.apply(request));
    }

    @GetMapping("/applications/mine")
    public ApiResponse<List<AssetApplication>> myApplications() {
        return ApiResponse.success(service.myApplications());
    }

    @GetMapping("/approvals")
    public ApiResponse<List<AssetApplication>> approvals() {
        return ApiResponse.success(service.approvals());
    }

    @PostMapping("/approvals/{id}/approve")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "通过资产申请",
            targetType = "media_asset_application",
            targetIdParameter = "id")
    public ApiResponse<AssetApplication> approve(
            @PathVariable Long id, @RequestBody AssetRequests.Decision request) {
        return ApiResponse.success(service.approve(id, request));
    }

    @PostMapping("/approvals/{id}/reject")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.UPDATE,
            name = "驳回资产申请",
            targetType = "media_asset_application",
            targetIdParameter = "id")
    public ApiResponse<AssetApplication> reject(
            @PathVariable Long id, @RequestBody AssetRequests.Decision request) {
        return ApiResponse.success(service.reject(id, request));
    }
}
