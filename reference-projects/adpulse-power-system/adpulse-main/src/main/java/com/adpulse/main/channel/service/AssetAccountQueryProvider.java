package com.adpulse.main.channel.service;

import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/** Doris 未启用时，以统一资产台账作为渠道账户查询范围。 */
@Component
@Primary
@ConditionalOnProperty(
        prefix = "adpulse.doris",
        name = "enabled",
        havingValue = "false",
        matchIfMissing = true)
public class AssetAccountQueryProvider implements AccountQueryProvider {
    private final ChannelMapper mapper;

    public AssetAccountQueryProvider(ChannelMapper mapper) {
        this.mapper = mapper;
    }

    /** 查询资产台账账户；平台快照字段由渠道服务批量补充。 */
    @Override
    public PageResult find(AccountQuery query, int offset, int pageSize) {
        return new PageResult(
                mapper.findAssetAccounts(query, offset, pageSize),
                mapper.countAssetAccounts(query));
    }

    /** 非 Doris 环境仅返回资产台账可提供的金额汇总。 */
    @Override
    public Aggregate summarize(AccountQuery query) {
        return mapper.summarizeAssetAccounts(query);
    }
}
