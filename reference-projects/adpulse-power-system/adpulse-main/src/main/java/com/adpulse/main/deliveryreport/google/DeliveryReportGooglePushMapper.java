package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Batch;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Item;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Template;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 项目Google日报模板及推送批次的MyBatis访问接口。 */
@Mapper
public interface DeliveryReportGooglePushMapper {
    List<Template> findTemplates();

    Template findTemplate(@Param("id") Long id);

    Template findTemplateByProject(@Param("projectId") Long projectId);

    int countActiveProject(@Param("projectId") Long projectId);

    String findProjectDailyReportUrl(@Param("projectId") Long projectId);

    int insertTemplate(Template template);

    int updateTemplate(Template template);

    int deleteTemplate(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    int insertBatch(Batch batch);

    int insertItem(Item item);

    List<Long> findPendingBatchIds(@Param("limit") int limit);

    int claimBatch(@Param("id") Long id);

    Batch findBatchForUser(@Param("id") Long id, @Param("userId") Long userId);

    List<Batch> findBatchesForUser(@Param("userId") Long userId, @Param("limit") int limit);

    List<Item> findItems(@Param("batchId") Long batchId);

    int claimItem(@Param("id") Long id);

    int completeItem(@Param("id") Long id, @Param("targetRow") int targetRow);

    int failItem(@Param("id") Long id, @Param("errorMessage") String errorMessage);

    int finishBatch(@Param("id") Long id, @Param("errorMessage") String errorMessage);

    int retryFailedItems(@Param("batchId") Long batchId);

    int resetBatchForRetry(@Param("id") Long id, @Param("userId") Long userId);

    int recoverStaleItems();

    int recoverStaleBatches();
}
