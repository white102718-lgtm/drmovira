package com.adpulse.main.manualtask;

import com.adpulse.system.common.api.ApiResponse;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 手动任务目录、触发与执行日志接口。 */
@RestController
@RequestMapping("/manual-tasks")
public class ManualTaskController {
    private final ManualTaskService service;

    public ManualTaskController(ManualTaskService service) {
        this.service = service;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('system:manual-task:list')")
    public ApiResponse<List<ManualTaskViews.Task>> tasks() {
        return ApiResponse.success(service.tasks());
    }

    @PostMapping("/{taskCode}/executions")
    @PreAuthorize("hasAuthority('system:manual-task:execute')")
    public ApiResponse<ManualTaskViews.Execution> trigger(
            @PathVariable String taskCode,
            @RequestBody(required = false) ManualTaskViews.TriggerRequest request) {
        return ApiResponse.success(service.trigger(taskCode, request));
    }

    @GetMapping("/executions")
    @PreAuthorize("hasAuthority('system:manual-task:list')")
    public ApiResponse<ManualTaskViews.Page> executions(
            @RequestParam(required = false) String taskCode,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.executions(taskCode, page, pageSize));
    }

    @GetMapping("/executions/{id}")
    @PreAuthorize("hasAuthority('system:manual-task:list')")
    public ApiResponse<ManualTaskViews.Execution> execution(@PathVariable Long id) {
        return ApiResponse.success(service.execution(id));
    }
}
