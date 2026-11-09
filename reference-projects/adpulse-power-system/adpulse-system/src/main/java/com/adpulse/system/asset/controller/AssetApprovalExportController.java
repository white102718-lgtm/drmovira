package com.adpulse.system.asset.controller;

import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.service.AssetApprovalExportService;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 审批中心文件导出端点，与审批写操作控制器保持职责分离。 */
@RestController
@RequestMapping("/asset-flow-v2/approvals")
public class AssetApprovalExportController {
    private static final MediaType XLSX =
            MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    private static final DateTimeFormatter FILE_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");

    private final AssetApprovalExportService exportService;

    public AssetApprovalExportController(AssetApprovalExportService exportService) {
        this.exportService = exportService;
    }

    /** 导出用户勾选的审批单及其最新办理结果。 */
    @PostMapping("/export")
    public ResponseEntity<byte[]> export(@Valid @RequestBody AssetRequests.ApprovalExport request) {
        byte[] content = exportService.export(request.ids());
        String fileName = "审批中心_" + FILE_TIME.format(LocalDateTime.now()) + ".xlsx";
        return ResponseEntity.ok()
                .contentType(XLSX)
                .contentLength(content.length)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(fileName, StandardCharsets.UTF_8)
                                .build()
                                .toString())
                .body(content);
    }
}
