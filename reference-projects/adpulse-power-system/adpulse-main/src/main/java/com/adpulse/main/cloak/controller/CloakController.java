package com.adpulse.main.cloak.controller;

import com.adpulse.main.cloak.dto.CloakRequests;
import com.adpulse.main.cloak.dto.CloakViews;
import com.adpulse.main.cloak.service.CloakService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 斗篷管理接口。 */
@RestController
@RequestMapping("/cloak")
public class CloakController {
    private final CloakService service;

    public CloakController(CloakService service) {
        this.service = service;
    }

    /** 查询推广域名下拉选项。 */
    @GetMapping("/domains")
    public ApiResponse<List<CloakViews.DomainOption>> domains() {
        return ApiResponse.success(service.listDomains());
    }

    /** 查询投放地区下拉选项。 */
    @GetMapping("/countries")
    public ApiResponse<List<CloakViews.CountryOption>> countries() {
        return ApiResponse.success(service.listCountries());
    }

    /** 查询项目中已经存在有效斗篷记录的代理线。 */
    @GetMapping("/projects/{projectId}/occupied-agency-lines")
    public ApiResponse<List<String>> occupiedAgencyLines(@PathVariable String projectId) {
        return ApiResponse.success(service.listOccupiedAgencyLineIds(projectId));
    }

    /** 批量创建斗篷并保存本地管理记录。 */
    @PostMapping("/batch")
    public ApiResponse<CloakViews.BatchResult> createBatch(
            @Valid @RequestBody CloakRequests.BatchCreate request) {
        return ApiResponse.success(service.createBatch(request));
    }

    /** 将成功创建的整批斗篷链接逐条回写到项目代理线Google Sheet。 */
    @PostMapping("/batches/{batchId}/sheet-writeback")
    public ApiResponse<CloakViews.SheetWritebackResult> writebackSheet(
            @PathVariable Long batchId) {
        return ApiResponse.success(service.writebackSheet(batchId));
    }

    /** 将斗篷管理列表选中的记录批量回填到对应项目代理线Google Sheet。 */
    @PostMapping("/records/sheet-writeback")
    public ApiResponse<CloakViews.RecordSheetWritebackResult> writebackRecords(
            @Valid @RequestBody CloakRequests.SheetWriteback request) {
        return ApiResponse.success(service.writebackRecords(request.recordIds()));
    }

    /** 分页查询已成功创建的斗篷管理记录。 */
    @GetMapping("/records")
    public ApiResponse<CloakViews.Page<CloakViews.Record>> records(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String projectId,
            @RequestParam(required = false) String country,
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "10") int pageSize) {
        return ApiResponse.success(
                service.listRecords(
                        keyword, projectId, country, startDate, endDate, page, pageSize));
    }

    /** 删除一条或多条斗篷，多个本地主键使用英文逗号分隔。 */
    @DeleteMapping("/records/{ids}")
    public ApiResponse<Void> deleteRecords(@PathVariable String ids) {
        service.deleteRecords(ids);
        return ApiResponse.success();
    }
}
