package com.adpulse.main.feishu.service;

import com.adpulse.main.feishu.client.FeishuProviderClient;
import com.adpulse.main.feishu.dto.FeishuDtos;
import com.adpulse.main.feishu.mapper.FeishuMapper;
import com.adpulse.main.feishu.model.FeishuModels;
import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import java.net.URI;
import java.util.List;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 飞书应用凭证、同步任务、字段映射和执行队列服务。 */
@Service
public class FeishuService {
    private final FeishuMapper mapper;
    private final FeishuProviderClient provider;
    private final IntegrationSecretCipher cipher;

    public FeishuService(
            FeishuMapper mapper, FeishuProviderClient provider, IntegrationSecretCipher cipher) {
        this.mapper = mapper;
        this.provider = provider;
        this.cipher = cipher;
    }

    /** 查询不包含App Secret的应用配置。 */
    public FeishuDtos.Config config() {
        FeishuModels.Config item = mapper.findConfig();
        return item == null
                ? new FeishuDtos.Config(null, "AdPulse 飞书应用", "")
                : new FeishuDtos.Config(
                        item.getId().toString(), item.getAppName(), item.getAppId());
    }

    /** 新增或更新飞书应用凭证，密钥仅以AES-GCM密文保存。 */
    @Transactional
    public FeishuDtos.Config saveConfig(FeishuDtos.ConfigSave request) {
        FeishuModels.Config item = mapper.findConfig();
        if (item == null && (request.appSecret() == null || request.appSecret().isBlank()))
            throw new FeishuException("首次配置必须填写App Secret");
        if (item == null) item = new FeishuModels.Config();
        item.setAppName(request.appName().trim());
        item.setAppId(request.appId().trim());
        item.setUpdatedBy(actorId());
        if (request.appSecret() != null && !request.appSecret().isBlank())
            item.setAppSecretCiphertext(cipher.encrypt(request.appSecret().trim()));
        if (item.getId() == null) mapper.insertConfig(item);
        else mapper.updateConfig(item);
        return new FeishuDtos.Config(item.getId().toString(), item.getAppName(), item.getAppId());
    }

    /** 查询全部飞书同步任务。 */
    public List<FeishuDtos.Task> tasks() {
        return mapper.findTasks().stream().map(this::taskView).toList();
    }

    /** 创建飞书同步任务。 */
    @Transactional
    public FeishuDtos.Task createTask(FeishuDtos.TaskSave request) {
        requireConfig(request.appId());
        FeishuModels.Task task = taskModel(null, request);
        mapper.insertTask(task, actorId());
        return taskView(requireTask(task.getId()));
    }

    /** 更新飞书同步任务。 */
    @Transactional
    public FeishuDtos.Task updateTask(Long id, FeishuDtos.TaskSave request) {
        requireTask(id);
        requireConfig(request.appId());
        FeishuModels.Task task = taskModel(id, request);
        mapper.updateTask(task, actorId());
        return taskView(requireTask(id));
    }

    /** 更新飞书任务启停状态。 */
    @Transactional
    public void updateStatus(Long id, Integer status) {
        requireTask(id);
        if (status == null || (status != 0 && status != 1)) throw new FeishuException("任务状态不合法");
        mapper.updateTaskStatus(id, status, actorId());
    }

    /** 软删除任务及其字段映射。 */
    @Transactional
    public void deleteTask(Long id) {
        requireTask(id);
        long deletedAt = System.currentTimeMillis();
        mapper.deleteMappings(id, deletedAt);
        mapper.deleteTask(id, deletedAt, actorId());
    }

    /** 查询任务字段映射。 */
    public List<FeishuDtos.Mapping> mappings(Long taskId) {
        requireTask(taskId);
        return mapper.findMappings(taskId).stream().map(this::mappingView).toList();
    }

    /** 原子替换任务全部字段映射。 */
    @Transactional
    public void saveMappings(Long taskId, List<FeishuDtos.Mapping> requests) {
        requireTask(taskId);
        long deletedAt = System.currentTimeMillis();
        mapper.deleteMappings(taskId, deletedAt);
        for (FeishuDtos.Mapping request : requests) {
            FeishuModels.Mapping item = new FeishuModels.Mapping();
            item.setTaskId(taskId);
            item.setSystemFieldName(request.systemFieldName().trim());
            item.setFeishuFieldName(request.feishuFieldName().trim());
            item.setColumnComment(request.columnComment());
            item.setDataType(request.dataType());
            item.setIsRequired(request.isRequired() == null ? 0 : request.isRequired());
            item.setIsSplit(request.isSplit() == null ? 0 : request.isSplit());
            mapper.insertMapping(item);
        }
    }

    /** 查询任务最近同步日志。 */
    public List<FeishuDtos.Log> logs(Long taskId) {
        requireTask(taskId);
        return mapper.findLogs(taskId).stream()
                .map(
                        item ->
                                new FeishuDtos.Log(
                                        item.getId().toString(),
                                        item.getStatus(),
                                        item.getTotalCount(),
                                        item.getSuccessCount(),
                                        item.getFailCount(),
                                        item.getErrorMessage(),
                                        item.getStartedAt(),
                                        item.getEndedAt()))
                .toList();
    }

    /** 将飞书全量同步写入新服务任务队列并记录待执行日志。 */
    @Transactional
    public void enqueueSync(Long taskId) {
        FeishuModels.Task task = requireTask(taskId);
        if (task.getStatus() != 1) throw new FeishuException("同步任务已停用");
        mapper.insertPendingLog(taskId);
        mapper.insertSyncJob("feishu", taskId.toString(), actorId());
    }

    /** 调用飞书开放平台验证当前任务连接。 */
    public void testConnection(Long taskId) {
        FeishuModels.Task task = requireTask(taskId);
        FeishuModels.Config config = requireConfig(task.getAppId());
        provider.fields(
                config.getAppId(),
                cipher.decrypt(config.getAppSecretCiphertext()),
                task.getAppToken(),
                task.getTableId());
    }

    /** 从飞书文档地址或App Token发现多维表格子表。 */
    public FeishuDtos.Discovery discover(FeishuDtos.DiscoverSave request) {
        FeishuModels.Config config = requireConfig(request.appId());
        String appToken = parseAppToken(request.appTokenOrUrl());
        return new FeishuDtos.Discovery(
                appToken,
                provider.tables(
                        config.getAppId(),
                        cipher.decrypt(config.getAppSecretCiphertext()),
                        appToken));
    }

    /** 查询任务飞书字段。 */
    public List<FeishuDtos.FieldOption> fields(Long taskId) {
        FeishuModels.Task task = requireTask(taskId);
        FeishuModels.Config config = requireConfig(task.getAppId());
        return provider.fields(
                config.getAppId(),
                cipher.decrypt(config.getAppSecretCiphertext()),
                task.getAppToken(),
                task.getTableId());
    }

    /** 查询当前数据库指定系统表字段，不拼接动态SQL。 */
    public List<FeishuDtos.SystemColumn> systemColumns(String tableName) {
        if (tableName == null || !tableName.matches("[A-Za-z][A-Za-z0-9_]{0,127}"))
            throw new FeishuException("系统表名称不合法");
        return mapper.findSystemColumns(tableName).stream()
                .map(
                        row ->
                                new FeishuDtos.SystemColumn(
                                        text(row.get("columnName")),
                                        text(row.get("columnComment"))))
                .toList();
    }

    private String parseAppToken(String input) {
        String value = input.trim();
        if (!value.startsWith("http")) return value;
        String path = URI.create(value).getPath();
        String[] segments = path.split("/");
        for (int index = 0; index < segments.length - 1; index++)
            if ("base".equals(segments[index]) || "sheets".equals(segments[index]))
                return segments[index + 1];
        throw new FeishuException("无法从飞书文档地址识别App Token");
    }

    private FeishuModels.Config requireConfig(String appId) {
        FeishuModels.Config config =
                appId == null || appId.isBlank()
                        ? mapper.findConfig()
                        : mapper.findConfigByAppId(appId);
        if (config == null) throw new FeishuException("请先配置飞书应用凭证");
        return config;
    }

    private FeishuModels.Task requireTask(Long id) {
        FeishuModels.Task task = mapper.findTask(id);
        if (task == null) throw new FeishuException("飞书同步任务不存在");
        return task;
    }

    private FeishuModels.Task taskModel(Long id, FeishuDtos.TaskSave request) {
        FeishuModels.Task task = new FeishuModels.Task();
        task.setId(id);
        task.setTaskName(request.taskName().trim());
        task.setAppId(request.appId().trim());
        task.setAppToken(request.appToken().trim());
        task.setTableId(request.tableId().trim());
        task.setTableName(request.tableName());
        task.setTargetTableName(request.targetTableName().trim());
        task.setTaskType(request.taskType());
        task.setStatus(request.status());
        return task;
    }

    private FeishuDtos.Task taskView(FeishuModels.Task item) {
        return new FeishuDtos.Task(
                item.getId().toString(),
                item.getTaskName(),
                item.getAppId(),
                item.getAppToken(),
                item.getTableId(),
                item.getTableName(),
                item.getTargetTableName(),
                item.getTaskType(),
                item.getStatus(),
                item.getLastSyncTime(),
                item.getCreatedAt());
    }

    private FeishuDtos.Mapping mappingView(FeishuModels.Mapping item) {
        return new FeishuDtos.Mapping(
                item.getId().toString(),
                item.getTaskId().toString(),
                item.getSystemFieldName(),
                item.getFeishuFieldName(),
                item.getColumnComment(),
                item.getDataType(),
                item.getIsRequired(),
                item.getIsSplit());
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    private Long actorId() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        throw new FeishuException("登录状态无效");
    }

    /** 可直接展示的飞书同步业务异常。 */
    public static class FeishuException extends RuntimeException {
        /** 创建飞书同步业务异常。 */
        public FeishuException(String message) {
            super(message);
        }
    }
}
