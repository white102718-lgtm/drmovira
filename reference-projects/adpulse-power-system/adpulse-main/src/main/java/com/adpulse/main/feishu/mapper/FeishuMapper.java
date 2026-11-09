package com.adpulse.main.feishu.mapper;

import com.adpulse.main.feishu.model.FeishuModels.Config;
import com.adpulse.main.feishu.model.FeishuModels.Log;
import com.adpulse.main.feishu.model.FeishuModels.Mapping;
import com.adpulse.main.feishu.model.FeishuModels.Task;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 飞书同步持久化接口。 */
@Mapper
public interface FeishuMapper {
    /** 查询当前飞书应用配置。 */
    Config findConfig();

    /** 按App ID查询配置。 */
    Config findConfigByAppId(@Param("appId") String appId);

    /** 新增飞书应用配置。 */
    int insertConfig(Config config);

    /** 更新飞书应用配置。 */
    int updateConfig(Config config);

    /** 查询全部同步任务。 */
    List<Task> findTasks();

    /** 按ID查询同步任务。 */
    Task findTask(@Param("id") Long id);

    /** 新增同步任务。 */
    int insertTask(@Param("task") Task task, @Param("actorId") Long actorId);

    /** 更新同步任务。 */
    int updateTask(@Param("task") Task task, @Param("actorId") Long actorId);

    /** 更新任务状态。 */
    int updateTaskStatus(
            @Param("id") Long id, @Param("status") Integer status, @Param("actorId") Long actorId);

    /** 软删除任务及其映射。 */
    int deleteTask(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("actorId") Long actorId);

    /** 查询任务字段映射。 */
    List<Mapping> findMappings(@Param("taskId") Long taskId);

    /** 软删除任务字段映射。 */
    int deleteMappings(@Param("taskId") Long taskId, @Param("deletedAt") long deletedAt);

    /** 新增任务字段映射。 */
    int insertMapping(Mapping mapping);

    /** 查询任务最近日志。 */
    List<Log> findLogs(@Param("taskId") Long taskId);

    /** 写入待执行同步日志。 */
    int insertPendingLog(@Param("taskId") Long taskId);

    /** 查询系统表字段。 */
    List<java.util.Map<String, Object>> findSystemColumns(@Param("tableName") String tableName);

    /** 写入第三方同步任务队列。 */
    int insertSyncJob(
            @Param("provider") String provider,
            @Param("businessId") String businessId,
            @Param("requestedBy") Long requestedBy);
}
