package com.adpulse.main.channel.service;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import java.util.List;

/** 跨账户主数据与广告日明细查询渠道账户。 */
public interface AccountQueryProvider {

    /** 查询满足账户条件和区间花费条件的分页数据。 */
    PageResult find(AccountQuery query, int offset, int pageSize);

    /** 按与列表相同的条件汇总账户金额。 */
    Aggregate summarize(AccountQuery query);

    /** 渠道账户分页查询结果。 */
    record PageResult(List<Account> items, long total) {}
}
