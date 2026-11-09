package com.adpulse.system.assetreturn.controller;

import com.adpulse.system.assetreturn.dto.AssetReturnRequests;
import com.adpulse.system.assetreturn.model.AssetReturn;
import com.adpulse.system.assetreturn.model.AssetReturnSummary;
import com.adpulse.system.assetreturn.service.AssetReturnService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 资产回收申请、查询与完成处理接口。 */
@RestController
@RequestMapping("/asset-returns")
@Tag(name = "资产回收", description = "已分配媒介资产的回收与重新入库")
public class AssetReturnController {
    private final AssetReturnService service;

    public AssetReturnController(AssetReturnService service) {
        this.service = service;
    }

    /** 查询回收单。 */
    @GetMapping
    @PreAuthorize("hasAuthority('media:resource:return:manage')")
    public ApiResponse<PageResult<AssetReturn>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String assetType,
            @RequestParam(required = false) String assetSubtype,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.page(keyword, status, assetType, assetSubtype, page, pageSize));
    }

    /** 查询回收处理概览。 */
    @GetMapping("/summary")
    @PreAuthorize("hasAuthority('media:resource:return:manage')")
    public ApiResponse<AssetReturnSummary> summary() {
        return ApiResponse.success(service.summary());
    }

    /** 由当前使用人或资源管理员发起回收。 */
    @PostMapping("/assets/{assetId}")
    @PreAuthorize("isAuthenticated()")
    @OperationAudit(
            module = "ASSET_RETURN",
            type = OperationType.CREATE,
            name = "发起资产回收",
            targetType = "media_asset",
            targetIdParameter = "assetId")
    public ApiResponse<AssetReturn> create(
            @PathVariable Long assetId, @Valid @RequestBody AssetReturnRequests.Create request) {
        return ApiResponse.success(service.create(assetId, request));
    }

    /** 由资源管理员完成回收。 */
    @PostMapping("/{id}/complete")
    @PreAuthorize("hasAuthority('media:resource:return:manage')")
    @OperationAudit(
            module = "ASSET_RETURN",
            type = OperationType.UPDATE,
            name = "完成资产回收",
            targetType = "media_asset_return",
            targetIdParameter = "id")
    public ApiResponse<AssetReturn> complete(
            @PathVariable Long id, @Valid @RequestBody AssetReturnRequests.Complete request) {
        return ApiResponse.success(service.complete(id, request));
    }
}
