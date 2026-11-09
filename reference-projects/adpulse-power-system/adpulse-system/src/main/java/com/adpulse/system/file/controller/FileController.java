package com.adpulse.system.file.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.file.dto.FileRequests;
import com.adpulse.system.file.dto.FileResponses;
import com.adpulse.system.file.model.StoredFile;
import com.adpulse.system.file.service.FileService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 通用文件预检、上传、查询、下载和删除接口。 */
@RestController
@RequestMapping("/files")
@Tag(name = "通用文件", description = "本地文件存储与SHA-256秒传")
public class FileController {
    private final FileService service;

    public FileController(FileService service) {
        this.service = service;
    }

    @PostMapping("/precheck")
    @OperationAudit(
            module = "FILE",
            type = OperationType.CREATE,
            name = "文件秒传预检",
            targetType = "sys_file")
    public ApiResponse<FileResponses.PrecheckResult> precheck(
            @Valid @RequestBody FileRequests.Precheck request) {
        return ApiResponse.success(service.precheck(request));
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @OperationAudit(
            module = "FILE",
            type = OperationType.CREATE,
            name = "上传文件",
            targetType = "sys_file")
    public ApiResponse<StoredFile> upload(
            @RequestPart("file") MultipartFile file,
            @RequestParam("contentHash") String contentHash) {
        return ApiResponse.success(service.upload(file, contentHash));
    }

    @GetMapping("/{id}")
    public ApiResponse<StoredFile> detail(@PathVariable Long id) {
        return ApiResponse.success(service.detail(id));
    }

    @GetMapping("/open/{id}")
    public ApiResponse<StoredFile> openDetail(@PathVariable Long id) {
        return ApiResponse.success(service.openDetail(id));
    }

    @GetMapping("/{id}/download")
    public ResponseEntity<Resource> download(@PathVariable Long id) {
        return downloadResponse(service.download(id));
    }

    @GetMapping("/open/{id}/download")
    public ResponseEntity<Resource> openDownload(@PathVariable Long id) {
        return downloadResponse(service.openDownload(id));
    }

    private ResponseEntity<Resource> downloadResponse(FileResponses.DownloadFile download) {
        StoredFile file = download.file();
        MediaType mediaType;
        try {
            mediaType = MediaType.parseMediaType(file.getMimeType());
        } catch (IllegalArgumentException exception) {
            mediaType = MediaType.APPLICATION_OCTET_STREAM;
        }
        return ResponseEntity.ok()
                .contentType(mediaType)
                .contentLength(file.getFileSize())
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(file.getOriginalName(), StandardCharsets.UTF_8)
                                .build()
                                .toString())
                .body(download.resource());
    }

    @DeleteMapping("/{id}")
    @OperationAudit(
            module = "FILE",
            type = OperationType.DELETE,
            name = "删除文件",
            targetType = "sys_file",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
