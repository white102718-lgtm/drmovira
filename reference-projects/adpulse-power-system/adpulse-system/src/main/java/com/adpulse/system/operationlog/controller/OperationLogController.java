package com.adpulse.system.operationlog.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.operationlog.model.OperationLog;
import com.adpulse.system.operationlog.service.OperationLogService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDateTime;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 系统管理操作审计日志查询接口。 */
@RestController
@RequestMapping("/operation-logs")
@Tag(name = "操作日志", description = "系统管理新增、修改、删除和安全重置记录")
@PreAuthorize("hasAuthority('system:user:list')")
public class OperationLogController {

    private final OperationLogService service;

    public OperationLogController(OperationLogService service) {
        this.service = service;
    }

    /** 按操作者、模块、动作、结果、IP和时间范围分页查询。 */
    @GetMapping
    public ApiResponse<PageResult<OperationLog>> page(
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) String moduleCode,
            @RequestParam(required = false) String operationType,
            @RequestParam(required = false) Integer operationResult,
            @RequestParam(required = false) String clientIp,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    LocalDateTime startedAt,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
                    LocalDateTime endedAt,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.page(
                        keyword,
                        moduleCode,
                        operationType,
                        operationResult,
                        clientIp,
                        startedAt,
                        endedAt,
                        page,
                        pageSize));
    }
}
