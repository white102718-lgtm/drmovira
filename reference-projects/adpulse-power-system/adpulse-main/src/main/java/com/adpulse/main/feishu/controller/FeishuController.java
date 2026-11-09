package com.adpulse.main.feishu.controller;

import com.adpulse.main.feishu.dto.FeishuDtos;
import com.adpulse.main.feishu.service.FeishuService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
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

/** 飞书同步配置、字段映射和执行任务接口。 */
@RestController
@RequestMapping("/feishu")
public class FeishuController {
    private final FeishuService service;

    public FeishuController(FeishuService service) {
        this.service = service;
    }

    /** 查询飞书应用配置。 */
    @GetMapping("/config")
    public ApiResponse<FeishuDtos.Config> config() {
        return ApiResponse.success(service.config());
    }

    /** 保存飞书应用配置。 */
    @PutMapping("/config")
    public ApiResponse<FeishuDtos.Config> saveConfig(
            @Valid @RequestBody FeishuDtos.ConfigSave request) {
        return ApiResponse.success(service.saveConfig(request));
    }

    /** 查询全部飞书同步任务。 */
    @GetMapping("/tasks")
    public ApiResponse<List<FeishuDtos.Task>> tasks() {
        return ApiResponse.success(service.tasks());
    }

    /** 创建飞书同步任务。 */
    @PostMapping("/tasks")
    public ApiResponse<FeishuDtos.Task> createTask(
            @Valid @RequestBody FeishuDtos.TaskSave request) {
        return ApiResponse.success(service.createTask(request));
    }

    /** 更新飞书同步任务。 */
    @PutMapping("/tasks/{id}")
    public ApiResponse<FeishuDtos.Task> updateTask(
            @PathVariable Long id, @Valid @RequestBody FeishuDtos.TaskSave request) {
        return ApiResponse.success(service.updateTask(id, request));
    }

    /** 软删除飞书同步任务。 */
    @DeleteMapping("/tasks/{id}")
    public ApiResponse<Void> deleteTask(@PathVariable Long id) {
        service.deleteTask(id);
        return ApiResponse.success();
    }

    /** 更新飞书任务启停状态。 */
    @PatchMapping("/tasks/{id}/status")
    public ApiResponse<Void> updateStatus(
            @PathVariable Long id, @Valid @RequestBody FeishuDtos.StatusSave request) {
        service.updateStatus(id, request.status());
        return ApiResponse.success();
    }

    /** 查询任务字段映射。 */
    @GetMapping("/tasks/{id}/mappings")
    public ApiResponse<List<FeishuDtos.Mapping>> mappings(@PathVariable Long id) {
        return ApiResponse.success(service.mappings(id));
    }

    /** 原子替换任务字段映射。 */
    @PutMapping("/tasks/{id}/mappings")
    public ApiResponse<Void> saveMappings(
            @PathVariable Long id, @Valid @RequestBody List<FeishuDtos.Mapping> requests) {
        service.saveMappings(id, requests);
        return ApiResponse.success();
    }

    /** 查询任务最近同步日志。 */
    @GetMapping("/tasks/{id}/logs")
    public ApiResponse<List<FeishuDtos.Log>> logs(@PathVariable Long id) {
        return ApiResponse.success(service.logs(id));
    }

    /** 创建飞书全量同步队列任务。 */
    @PostMapping("/tasks/{id}/sync")
    public ApiResponse<Void> sync(@PathVariable Long id) {
        service.enqueueSync(id);
        return ApiResponse.success();
    }

    /** 验证飞书任务连接。 */
    @PostMapping("/tasks/{id}/connection-test")
    public ApiResponse<Void> connectionTest(@PathVariable Long id) {
        service.testConnection(id);
        return ApiResponse.success();
    }

    /** 查询任务飞书字段。 */
    @GetMapping("/tasks/{id}/fields")
    public ApiResponse<List<FeishuDtos.FieldOption>> fields(@PathVariable Long id) {
        return ApiResponse.success(service.fields(id));
    }

    /** 从文档地址或App Token发现飞书子表。 */
    @PostMapping("/tables/discover")
    public ApiResponse<FeishuDtos.Discovery> discover(
            @Valid @RequestBody FeishuDtos.DiscoverSave request) {
        return ApiResponse.success(service.discover(request));
    }

    /** 查询可映射的系统表字段。 */
    @GetMapping("/system-columns")
    public ApiResponse<List<FeishuDtos.SystemColumn>> systemColumns(
            @RequestParam String tableName) {
        return ApiResponse.success(service.systemColumns(tableName));
    }
}
