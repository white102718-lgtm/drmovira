package com.adpulse.main.google.mapper;

import com.adpulse.main.google.model.GoogleModels.Account;
import com.adpulse.main.google.model.GoogleModels.Mapping;
import com.adpulse.main.google.model.GoogleModels.SyncData;
import com.adpulse.main.google.model.GoogleModels.SyncJob;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** Google账号与Sheets映射持久化接口。 */
@Mapper
public interface GoogleIntegrationMapper {
    /** 查询全部有效Google账号。 */
    List<Account> findAccounts();

    /** 按ID查询Google账号。 */
    Account findAccount(@Param("id") Long id);

    /** 按Google subject查询账号。 */
    Account findAccountBySubject(@Param("subject") String subject);

    /** 新增Google账号。 */
    int insertAccount(Account account);

    /** 更新Google账号及加密令牌。 */
    int updateAccount(Account account);

    /** 更新账号授权状态。 */
    int updateAccountStatus(
            @Param("id") Long id, @Param("status") Integer status, @Param("actorId") Long actorId);

    /** 软删除Google账号。 */
    int deleteAccount(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("actorId") Long actorId);

    /** 查询账号映射。 */
    List<Mapping> findMappingsByAccount(@Param("accountId") Long accountId);

    /** 按ID查询映射。 */
    Mapping findMapping(@Param("id") Long id);

    /** 新增映射。 */
    int insertMapping(Mapping mapping);

    /** 更新映射。 */
    int updateMapping(Mapping mapping);

    /** 更新映射状态。 */
    int updateMappingStatus(
            @Param("id") Long id,
            @Param("enableFlag") Integer enableFlag,
            @Param("actorId") Long actorId);

    /** 软删除映射。 */
    int deleteMapping(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("actorId") Long actorId);

    /** 软删除账号全部映射。 */
    int deleteMappingsByAccount(
            @Param("accountId") Long accountId,
            @Param("deletedAt") long deletedAt,
            @Param("actorId") Long actorId);

    /** 写入Google映射同步队列。 */
    int insertSyncJob(
            @Param("businessId") String businessId,
            @Param("requestedBy") Long requestedBy,
            @Param("fullSync") boolean fullSync);

    /** 查询等待执行的Google同步任务。 */
    List<SyncJob> findPendingSyncJobs(@Param("limit") int limit);

    /** 以原子状态更新认领同步任务。 */
    int claimSyncJob(@Param("id") Long id);

    /** 标记同步任务成功。 */
    int completeSyncJob(@Param("id") Long id);

    /** 标记同步任务失败。 */
    int failSyncJob(@Param("id") Long id, @Param("errorMessage") String errorMessage);

    /** 查询需要自动调度的Google映射。 */
    List<Mapping> findAutoSyncMappings();

    /** 避免同一映射重复进入待执行队列。 */
    int countActiveSyncJobs(@Param("businessId") String businessId);

    /** 分页查询指定Google映射的同步任务日志。 */
    List<SyncJob> findSyncLogs(
            @Param("businessId") String businessId,
            @Param("offset") int offset,
            @Param("limit") int limit);

    /** 统计指定Google映射的同步任务日志。 */
    long countSyncLogs(@Param("businessId") String businessId);

    /** 更新映射最后成功同步时间。 */
    int updateMappingLastSyncTime(@Param("id") Long id);

    /** 新增或更新Google同步结果。 */
    int upsertSyncData(SyncData data);

    /** 分页查询指定映射的同步结果。 */
    List<SyncData> findSyncData(
            @Param("mappingId") Long mappingId,
            @Param("startDate") String startDate,
            @Param("endDate") String endDate,
            @Param("taskName") String taskName,
            @Param("offset") int offset,
            @Param("limit") int limit);

    /** 统计指定映射的同步结果。 */
    long countSyncData(
            @Param("mappingId") Long mappingId,
            @Param("startDate") String startDate,
            @Param("endDate") String endDate,
            @Param("taskName") String taskName);
}
