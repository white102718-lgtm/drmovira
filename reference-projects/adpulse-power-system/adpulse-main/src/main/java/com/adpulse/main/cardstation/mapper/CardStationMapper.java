package com.adpulse.main.cardstation.mapper;

import com.adpulse.main.cardstation.dto.CardStationRequests.CardQuery;
import com.adpulse.main.cardstation.model.CardStationModels.Balance;
import com.adpulse.main.cardstation.model.CardStationModels.Card;
import com.adpulse.main.cardstation.model.CardStationModels.LimitRecord;
import com.adpulse.main.cardstation.model.CardStationModels.LimitRule;
import com.adpulse.main.cardstation.model.CardStationModels.Statistics;
import java.math.BigDecimal;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 卡台管理持久化接口。 */
@Mapper
public interface CardStationMapper {
    /** 分页查询卡片。 */
    List<Card> findCards(
            @Param("query") CardQuery query,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    /** 统计卡片数量。 */
    long countCards(@Param("query") CardQuery query);

    /** 按第三方标识查询卡片。 */
    Card findCard(@Param("platform") String platform, @Param("cardId") String cardId);

    /** 查询卡台余额。 */
    List<Balance> findBalances(@Param("platform") String platform);

    /** 查询卡台统计。 */
    Statistics summarize(@Param("platform") String platform);

    /** 更新卡片限额。 */
    int updateLimit(
            @Param("platform") String platform,
            @Param("cardId") String cardId,
            @Param("amount") BigDecimal amount,
            @Param("preset") String preset);

    /** 更新卡片状态。 */
    int updateStatus(
            @Param("platform") String platform,
            @Param("cardId") String cardId,
            @Param("status") String status);

    /** 写入限额调整任务。 */
    int insertLimitRecord(
            @Param("platform") String platform,
            @Param("cardId") String cardId,
            @Param("oldAmount") BigDecimal oldAmount,
            @Param("newAmount") BigDecimal newAmount,
            @Param("preset") String preset,
            @Param("createdBy") Long createdBy);

    /** 分页查询限额调整记录。 */
    List<LimitRecord> findLimitRecords(
            @Param("platform") String platform,
            @Param("cardId") String cardId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    /** 统计限额调整记录。 */
    long countLimitRecords(@Param("platform") String platform, @Param("cardId") String cardId);

    /** 查询当前有效的卡台限额规则。 */
    LimitRule findLimitRule();

    /** 原子新增或更新卡台限额规则。 */
    int upsertLimitRule(
            @Param("dailyPeriod") Integer dailyPeriod,
            @Param("adjustAmount") BigDecimal adjustAmount,
            @Param("minAmount") BigDecimal minAmount,
            @Param("autoAdjustEnabled") Boolean autoAdjustEnabled,
            @Param("updatedBy") Long updatedBy);

    /** 单独更新卡台自动调额开关。 */
    int updateLimitRuleAutoAdjust(
            @Param("id") Long id,
            @Param("enabled") Boolean enabled,
            @Param("updatedBy") Long updatedBy);

    /** 创建第三方同步队列任务。 */
    int insertSyncJob(
            @Param("provider") String provider,
            @Param("jobType") String jobType,
            @Param("businessId") String businessId,
            @Param("requestPayload") String requestPayload,
            @Param("requestedBy") Long requestedBy);

    /** 查询最近插入任务ID。 */
    Long lastInsertId();
}
