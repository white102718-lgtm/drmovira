package com.adpulse.main.cloak.mapper;

import com.adpulse.main.cloak.model.CloakBatch;
import com.adpulse.main.cloak.model.CloakRecord;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 斗篷批次与管理列表持久化。 */
@Mapper
public interface CloakMapper {
    CloakBatch findBatchByRequestId(@Param("requestId") String requestId);

    CloakBatch findSuccessfulBatchById(@Param("id") Long id);

    int insertBatch(CloakBatch batch);

    int resetBatch(@Param("id") Long id, @Param("requestedBy") Long requestedBy);

    int insertRecord(CloakRecord record);

    int resetRecords(@Param("batchId") Long batchId, @Param("updatedBy") Long updatedBy);

    int markBatchSuccess(
            @Param("id") Long id,
            @Param("successCount") int successCount,
            @Param("providerMessage") String providerMessage);

    int markBatchFailed(
            @Param("id") Long id,
            @Param("status") int status,
            @Param("errorMessage") String errorMessage);

    int updateRecordStatus(
            @Param("batchId") Long batchId,
            @Param("status") int status,
            @Param("updatedBy") Long updatedBy);

    /** 将成功批次生成的推广链接按代理线主键回填到代理线列表。 */
    int updateAgencyLineCloakUrlsByBatch(
            @Param("batchId") Long batchId, @Param("updatedBy") Long updatedBy);

    List<CloakRecord> findRecords(
            @Param("keyword") String keyword,
            @Param("projectId") Long projectId,
            @Param("country") String country,
            @Param("startDate") String startDate,
            @Param("endDate") String endDate,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countRecords(
            @Param("keyword") String keyword,
            @Param("projectId") Long projectId,
            @Param("country") String country,
            @Param("startDate") String startDate,
            @Param("endDate") String endDate);

    List<CloakRecord> findRecordsByIds(@Param("ids") List<Long> ids);

    List<CloakRecord> findRecordsByBatchId(@Param("batchId") Long batchId);

    List<Long> findOccupiedAgencyLineIds(
            @Param("agencyLineIds") List<Long> agencyLineIds,
            @Param("requestId") String requestId);

    int updateSheetWriteback(
            @Param("id") Long id,
            @Param("status") int status,
            @Param("message") String message,
            @Param("rowNumber") Integer rowNumber,
            @Param("updatedBy") Long updatedBy);

    int softDeleteRecords(
            @Param("ids") List<Long> ids,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}
