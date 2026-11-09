package com.adpulse.main.channel.mapper;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelQuery;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.AccountChannel;
import com.adpulse.main.channel.model.ChannelModels.AccountType;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import com.adpulse.main.channel.model.ChannelModels.Campaign;
import com.adpulse.main.channel.model.ChannelModels.Channel;
import com.adpulse.main.channel.model.ChannelModels.Department;
import com.adpulse.main.channel.model.ChannelModels.Goods;
import com.adpulse.main.channel.model.ChannelModels.Pitcher;
import com.adpulse.main.channel.model.ChannelModels.Rate;
import com.adpulse.main.channel.model.ChannelModels.TypeSummary;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 渠道管理持久化接口。 */
@Mapper
public interface ChannelMapper {
    /** 从统一资产台账查询渠道账户基础数据。 */
    List<Account> findAssetAccounts(
            @Param("query") AccountQuery query,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countAssetAccounts(@Param("query") AccountQuery query);

    Aggregate summarizeAssetAccounts(@Param("query") AccountQuery query);

    /** 按稳定渠道 ID 查询账户 ID，渠道名称不参与关联。 */
    List<String> findAccountIdsByChannelId(@Param("channelId") Long channelId);

    /** 批量查询指定渠道下的账户，用于聚合平台余额快照。 */
    List<AccountChannel> findAccountChannelsByChannelIds(
            @Param("channelIds") List<Long> channelIds);

    /** 查询符合渠道筛选条件的账户，用于汇总平台余额快照。 */
    List<AccountChannel> findAccountChannelsByChannelQuery(@Param("query") ChannelQuery query);

    List<Channel> findChannels(
            @Param("query") ChannelQuery query,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countChannels(@Param("query") ChannelQuery query);

    Aggregate summarizeChannels(@Param("query") ChannelQuery query);

    List<TypeSummary> findTypeSummaries(
            @Param("query") ChannelQuery query,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countTypeSummaries(@Param("query") ChannelQuery query);

    Channel findChannel(@Param("id") Long id);

    /** 按飞书同步记录中的渠道名称定位有效渠道。 */
    Channel findChannelByName(@Param("channelName") String channelName);

    BigDecimal sumChannelSpend(
            @Param("channelId") Long channelId, @Param("spendDate") LocalDate spendDate);

    int insertChannel(Channel channel);

    int updateChannel(Channel channel);

    int softDeleteChannel(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    List<Rate> findRates(
            @Param("channelId") Long channelId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countRates(@Param("channelId") Long channelId);

    Rate findRate(@Param("id") Long id);

    int countRateOverlaps(
            @Param("channelId") Long channelId,
            @Param("excludedId") Long excludedId,
            @Param("effectiveDate") LocalDate effectiveDate,
            @Param("expiryDate") LocalDate expiryDate);

    int insertRate(Rate rate);

    int updateRate(Rate rate);

    List<AccountType> findAccountTypes();

    AccountType findAccountType(@Param("id") Long id);

    AccountType findAccountTypeByName(@Param("accountType") String accountType);

    int insertAccountType(AccountType accountType);

    int softDeleteAccountType(@Param("id") Long id, @Param("deletedAt") long deletedAt);

    long countAccountsByChannelId(@Param("channelId") Long channelId);

    Account findAccount(@Param("accountId") String accountId);

    Goods findGoods(@Param("channelId") Long channelId);

    int insertGoods(Goods goods);

    int updateGoods(Goods goods);

    int updateGoodsPutaway(
            @Param("channelId") Long channelId,
            @Param("putawayStatus") Integer putawayStatus,
            @Param("updatedBy") Long updatedBy);

    int updateChannelPutaway(
            @Param("channelId") Long channelId,
            @Param("putawayStatus") Integer putawayStatus,
            @Param("updatedBy") Long updatedBy);

    List<Campaign> findCampaigns(
            @Param("accountId") String accountId,
            @Param("campaignName") String campaignName,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countCampaigns(
            @Param("accountId") String accountId,
            @Param("campaignName") String campaignName,
            @Param("startDate") LocalDate startDate,
            @Param("endDate") LocalDate endDate);

    List<Pitcher> findPitchers(
            @Param("keyword") String keyword,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long countPitchers(@Param("keyword") String keyword);

    Pitcher findPitcher(@Param("id") Long id);

    List<Department> findDepartments();
}
