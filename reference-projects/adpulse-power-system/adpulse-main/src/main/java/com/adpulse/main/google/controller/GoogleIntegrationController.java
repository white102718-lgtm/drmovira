package com.adpulse.main.google.controller;

import com.adpulse.main.google.dto.GoogleDtos;
import com.adpulse.main.google.service.GoogleIntegrationService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
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
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Google OAuth账号、Drive/Sheets读取与映射管理接口。 */
@RestController
@RequestMapping("/data-integration")
public class GoogleIntegrationController {
    private final GoogleIntegrationService service;

    public GoogleIntegrationController(GoogleIntegrationService service) {
        this.service = service;
    }

    /** 查询Google账号及其映射。 */
    @GetMapping("/accounts")
    public ApiResponse<List<GoogleDtos.Account>> accounts() {
        return ApiResponse.success(service.accounts());
    }

    /** 生成Google OAuth授权地址。 */
    @GetMapping("/oauth/authorize")
    public ApiResponse<String> authorize() {
        return ApiResponse.success(service.authorizeUrl());
    }

    /** 处理Google OAuth回调。 */
    @GetMapping("/oauth/callback")
    public ResponseEntity<String> callback(@RequestParam String code, @RequestParam String state) {
        service.oauthCallback(code, state);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_HTML)
                .body(
                        "<!doctype html><meta charset=\"utf-8\"><title>Google授权成功</title><p>Google账号授权成功，可以关闭此页面。</p>");
    }

    /** 断开Google账号。 */
    @PostMapping("/accounts/{id}/disconnect")
    public ApiResponse<Void> disconnect(@PathVariable Long id) {
        service.disconnect(id);
        return ApiResponse.success();
    }

    /** 重新生成Google OAuth授权地址。 */
    @PostMapping("/accounts/{id}/reauthorize")
    public ApiResponse<String> reauthorize(@PathVariable Long id) {
        String authorizeUrl = service.authorizeUrl();
        service.disconnect(id);
        return ApiResponse.success(authorizeUrl);
    }

    /** 软删除Google账号及其映射。 */
    @DeleteMapping("/accounts/{id}")
    public ApiResponse<Void> deleteAccount(@PathVariable Long id) {
        service.deleteAccount(id);
        return ApiResponse.success();
    }

    /** 查询Google Drive中的Sheets文件。 */
    @GetMapping("/files")
    public ApiResponse<List<GoogleDtos.DriveFile>> files(
            @RequestParam Long accountId, @RequestParam(required = false) String keyword) {
        return ApiResponse.success(service.files(accountId, keyword));
    }

    /** 查询Spreadsheet子表。 */
    @GetMapping("/sheets")
    public ApiResponse<List<GoogleDtos.SheetTab>> sheets(
            @RequestParam Long accountId, @RequestParam String fileId) {
        return ApiResponse.success(service.sheets(accountId, fileId));
    }

    /** 查询Sheet第一行字段。 */
    @GetMapping("/columns")
    public ApiResponse<List<String>> columns(
            @RequestParam Long accountId,
            @RequestParam String fileId,
            @RequestParam String sheetName) {
        return ApiResponse.success(service.columns(accountId, fileId, sheetName));
    }

    /** 创建Google Sheets映射。 */
    @PostMapping("/mappings")
    public ApiResponse<String> createMapping(@Valid @RequestBody GoogleDtos.MappingSave request) {
        return ApiResponse.success(service.createMapping(request));
    }

    /** 查询Google Sheets映射详情。 */
    @GetMapping("/mappings/{id}")
    public ApiResponse<GoogleDtos.Mapping> mapping(@PathVariable Long id) {
        return ApiResponse.success(service.mapping(id));
    }

    /** 分页查询Google Sheets同步结果。 */
    @GetMapping("/mappings/{id}/sync-data")
    public ApiResponse<GoogleDtos.SyncDataPage> syncData(
            @PathVariable Long id,
            @RequestParam(required = false) String startDate,
            @RequestParam(required = false) String endDate,
            @RequestParam(required = false) String taskName,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer pageSize) {
        return ApiResponse.success(
                service.syncData(id, startDate, endDate, taskName, page, pageSize));
    }

    /** 分页查询Google Sheets映射同步任务日志。 */
    @GetMapping("/mappings/{id}/sync-logs")
    public ApiResponse<GoogleDtos.SyncLogPage> syncLogs(
            @PathVariable Long id,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer pageSize) {
        return ApiResponse.success(service.syncLogs(id, page, pageSize));
    }

    /** 更新Google Sheets映射。 */
    @PutMapping("/mappings/{id}")
    public ApiResponse<Void> updateMapping(
            @PathVariable Long id, @Valid @RequestBody GoogleDtos.MappingSave request) {
        service.updateMapping(id, request);
        return ApiResponse.success();
    }

    /** 更新映射启停状态。 */
    @PatchMapping("/mappings/{id}/status")
    public ApiResponse<Void> updateStatus(
            @PathVariable Long id, @Valid @RequestBody GoogleDtos.StatusSave request) {
        service.updateStatus(id, request.enableFlag());
        return ApiResponse.success();
    }

    /** 将Google映射同步写入新服务任务队列。 */
    @PostMapping("/mappings/{id}/sync")
    public ApiResponse<Void> sync(@PathVariable Long id) {
        service.enqueueSync(id);
        return ApiResponse.success();
    }

    /** 软删除Google Sheets映射。 */
    @DeleteMapping("/mappings/{id}")
    public ApiResponse<Void> deleteMapping(@PathVariable Long id) {
        service.deleteMapping(id);
        return ApiResponse.success();
    }
}
