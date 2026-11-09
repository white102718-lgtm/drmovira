package com.adpulse.main.channel.service;

import com.adpulse.main.adaccountasset.AdAccountAssetMapper;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAsset;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentSave;
import com.adpulse.main.adaccountasset.AdAccountAssetService;
import com.adpulse.main.channel.dto.ChannelRequests;
import com.adpulse.main.channel.dto.ChannelRequests.AccountBatch;
import com.adpulse.main.channel.dto.ChannelRequests.AccountImportItem;
import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.AccountTypeSave;
import com.adpulse.main.channel.dto.ChannelRequests.AvailableAccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelSave;
import com.adpulse.main.channel.dto.ChannelRequests.GoodsSave;
import com.adpulse.main.channel.dto.ChannelRequests.RateSave;
import com.adpulse.main.channel.dto.ChannelViews;
import com.adpulse.main.channel.mapper.ChannelMapper;
import com.adpulse.main.channel.model.ChannelModels.Account;
import com.adpulse.main.channel.model.ChannelModels.AccountChannel;
import com.adpulse.main.channel.model.ChannelModels.AccountType;
import com.adpulse.main.channel.model.ChannelModels.Aggregate;
import com.adpulse.main.channel.model.ChannelModels.Channel;
import com.adpulse.main.channel.model.ChannelModels.Department;
import com.adpulse.main.channel.model.ChannelModels.Goods;
import com.adpulse.main.channel.model.ChannelModels.Rate;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 渠道、费率、关联账户与上架信息业务服务。 */
@Service
public class ChannelService {
    private static final BigDecimal ZERO = BigDecimal.ZERO;
    private final ChannelMapper mapper;
    private final ChannelExcelCodec excelCodec;
    private final AccountSnapshotProvider accountSnapshotProvider;
    private final AccountQueryProvider accountQueryProvider;
    private final AdAccountAssetMapper adAccountAssetMapper;
    private final AdAccountAssetService adAccountAssetService;

    public ChannelService(
            ChannelMapper mapper,
            ChannelExcelCodec excelCodec,
            AccountSnapshotProvider accountSnapshotProvider,
            AccountQueryProvider accountQueryProvider,
            AdAccountAssetMapper adAccountAssetMapper,
            AdAccountAssetService adAccountAssetService) {
        this.mapper = mapper;
        this.excelCodec = excelCodec;
        this.accountSnapshotProvider = accountSnapshotProvider;
        this.accountQueryProvider = accountQueryProvider;
        this.adAccountAssetMapper = adAccountAssetMapper;
        this.adAccountAssetService = adAccountAssetService;
    }

    /** 分页查询渠道。 */
    public ChannelViews.Page<ChannelViews.ChannelDetail> listChannels(ChannelQuery query) {
        int page = safePage(query.page());
        int size = safeSize(query.pageSize());
        List<Channel> channels = mapper.findChannels(query, (page - 1) * size, size);
        enrichChannelBalances(
                channels,
                channels.isEmpty()
                        ? List.of()
                        : mapper.findAccountChannelsByChannelIds(
                                channels.stream().map(Channel::getId).toList()));
        List<ChannelViews.ChannelDetail> items = channels.stream().map(this::channelView).toList();
        return new ChannelViews.Page<>(items, mapper.countChannels(query), page, size);
    }

    /** 查询渠道汇总。 */
    public ChannelViews.ChannelSummary summarizeChannels(ChannelQuery query) {
        Aggregate value = mapper.summarizeChannels(query);
        if (value != null) {
            value.setTotalBalance(
                    sumSnapshotBalances(mapper.findAccountChannelsByChannelQuery(query)));
        }
        return new ChannelViews.ChannelSummary(
                longValue(value == null ? null : value.getChannelCount()),
                longValue(value == null ? null : value.getAccountCount()),
                money(value == null ? null : value.getTotalConsumption()),
                money(value == null ? null : value.getRechargeAmount()),
                money(value == null ? null : value.getTotalBalance()));
    }

    /** 分页查询账户类型维度汇总。 */
    public ChannelViews.Page<ChannelViews.ChannelTypeSummary> listTypeSummaries(
            ChannelQuery query) {
        int page = safePage(query.page());
        int size = safeSize(query.pageSize());
        var items =
                mapper.findTypeSummaries(query, (page - 1) * size, size).stream()
                        .map(
                                item ->
                                        new ChannelViews.ChannelTypeSummary(
                                                stringId(item.getId()),
                                                item.getAccountType(),
                                                item.getSubjectName(),
                                                item.getChannelName(),
                                                item.getChannelType(),
                                                money(item.getTotalConsumption()),
                                                item.getUsageStatus()))
                        .toList();
        return new ChannelViews.Page<>(items, mapper.countTypeSummaries(query), page, size);
    }

    /** 查询渠道详情。 */
    public ChannelViews.ChannelDetail getChannel(Long id) {
        Channel channel = requireChannel(id);
        enrichChannelBalances(
                List.of(channel), mapper.findAccountChannelsByChannelIds(List.of(id)));
        return channelView(channel);
    }

    /**
     * 查询打款申请所需的渠道快照。
     *
     * <p>昨日消耗按广告系列日花费汇总，收款地址读取渠道当前配置；申请提交时仍会把返回值固化到申请快照。
     */
    public ChannelViews.ChannelPaymentContext getPaymentContext(Long id) {
        Channel channel = requireChannel(id);
        BigDecimal yesterdaySpend = mapper.sumChannelSpend(id, LocalDate.now().minusDays(1));
        return new ChannelViews.ChannelPaymentContext(
                stringId(channel.getId()),
                channel.getChannelName(),
                money(yesterdaySpend),
                channel.getPaymentAddress());
    }

    /** 创建渠道。 */
    @Transactional
    public ChannelViews.ChannelDetail createChannel(ChannelSave request) {
        validateRequiredChannel(request);
        Channel channel = new Channel();
        mergeChannel(channel, request);
        channel.setPutawayStatus(0);
        channel.setBuyoutAmount(money(request.buyoutAmount()));
        channel.setRechargeAmount(money(request.rechargeAmount()));
        channel.setCreatedBy(actorId());
        channel.setUpdatedBy(actorId());
        try {
            mapper.insertChannel(channel);
        } catch (DuplicateKeyException exception) {
            throw new ChannelException("渠道编码或名称已存在");
        }
        return getChannel(channel.getId());
    }

    /** 修改渠道，未传字段保持原值。 */
    @Transactional
    public ChannelViews.ChannelDetail updateChannel(Long id, ChannelSave request) {
        Channel channel = requireChannel(id);
        mergeChannel(channel, request);
        channel.setUpdatedBy(actorId());
        try {
            mapper.updateChannel(channel);
        } catch (DuplicateKeyException exception) {
            throw new ChannelException("渠道编码或名称已存在");
        }
        return getChannel(id);
    }

    /** 软删除渠道；存在有效账户时拒绝删除。 */
    @Transactional
    public void deleteChannel(Long id) {
        requireChannel(id);
        if (mapper.countAccountsByChannelId(id) > 0) {
            throw new ChannelException("渠道仍有关联账户，不能删除");
        }
        mapper.softDeleteChannel(id, System.currentTimeMillis(), actorId());
    }

    /** 分页查询渠道费率。 */
    public ChannelViews.Page<ChannelViews.Rate> listRates(Long channelId, int page, int pageSize) {
        requireChannel(channelId);
        int safePage = safePage(page);
        int safeSize = safeSize(pageSize);
        var items =
                mapper.findRates(channelId, (safePage - 1) * safeSize, safeSize).stream()
                        .map(this::rateView)
                        .toList();
        return new ChannelViews.Page<>(items, mapper.countRates(channelId), safePage, safeSize);
    }

    /** 创建渠道费率，生效区间不可重叠。 */
    @Transactional
    public ChannelViews.Rate createRate(Long channelId, RateSave request) {
        requireChannel(channelId);
        validateRate(channelId, null, request);
        Rate rate = new Rate();
        rate.setChannelId(channelId);
        applyRate(rate, request);
        rate.setCreatedBy(actorId());
        rate.setUpdatedBy(actorId());
        mapper.insertRate(rate);
        return rateView(Objects.requireNonNull(mapper.findRate(rate.getId())));
    }

    /** 修改渠道费率。 */
    @Transactional
    public ChannelViews.Rate updateRate(Long channelId, Long rateId, RateSave request) {
        Rate rate = mapper.findRate(rateId);
        if (rate == null || !channelId.equals(rate.getChannelId())) {
            throw new ChannelException("费率不存在");
        }
        validateRate(channelId, rateId, request);
        applyRate(rate, request);
        rate.setUpdatedBy(actorId());
        mapper.updateRate(rate);
        return rateView(Objects.requireNonNull(mapper.findRate(rateId)));
    }

    /** 查询全部账户类型。 */
    public List<ChannelViews.AccountType> listAccountTypes() {
        return mapper.findAccountTypes().stream().map(this::accountTypeView).toList();
    }

    /** 新增账户类型。 */
    @Transactional
    public ChannelViews.AccountType createAccountType(AccountTypeSave request) {
        AccountType model = new AccountType();
        model.setAccountType(request.accountType().trim());
        model.setCreatedBy(actorId());
        try {
            mapper.insertAccountType(model);
        } catch (DuplicateKeyException exception) {
            throw new ChannelException("账户类型名称已存在");
        }
        return accountTypeView(Objects.requireNonNull(mapper.findAccountType(model.getId())));
    }

    /** 删除账户类型并将已绑定账户改为未分类。 */
    @Transactional
    public void deleteAccountType(Long id) {
        AccountType type = mapper.findAccountType(id);
        if (type == null) throw new ChannelException("账户类型不存在");
        Long operatorId = actorId();
        adAccountAssetMapper.detachAccountType(type.getAccountType(), operatorId);
        mapper.softDeleteAccountType(id, System.currentTimeMillis());
    }

    /** 分页查询渠道账户；未传花费时间时仅返回基础账户数据。 */
    public ChannelViews.Page<ChannelViews.Account> listAccounts(AccountQuery query) {
        validateOptionalSpendDateRange(query);
        int page = safePage(query.page());
        int size = safeSize(query.pageSize());
        AccountQueryProvider.PageResult result =
                accountQueryProvider.find(query, (page - 1) * size, size);
        List<Account> accounts = result.items();
        long total = result.total();
        enrichAccountSnapshots(accounts);
        var items = accounts.stream().map(this::accountView).toList();
        return new ChannelViews.Page<>(items, total, page, size);
    }

    /** 查询广告户申请办理账户，不依赖 Doris 花费区间数据。 */
    public ChannelViews.Page<ChannelViews.Account> listAvailableAccounts(
            AvailableAccountQuery query) {
        requireChannel(query.channelId());
        int page = safePage(query.page());
        int size = safeSize(query.pageSize());
        List<com.adpulse.main.adaccountasset.AdAccountAssetViews.Account> accounts =
                listChannelAssetAccounts(query.channelId()).stream()
                        .filter(
                                account ->
                                        query.accountType() == null
                                                || query.accountType()
                                                        .equals(account.accountType()))
                        .filter(
                                account ->
                                        query.accountIds() == null
                                                || query.accountIds().isEmpty()
                                                || query.accountIds().contains(account.accountId()))
                        .filter(
                                account ->
                                        query.status() == null
                                                || query.status().equals(account.accountStatus()))
                        .filter(
                                account ->
                                        query.usageStatus() == null
                                                || query.usageStatus()
                                                        .equals(
                                                                account.assignments().isEmpty()
                                                                        ? 0
                                                                        : 1))
                        .toList();
        int from = Math.min((page - 1) * size, accounts.size());
        int to = Math.min(from + size, accounts.size());
        List<ChannelViews.Account> items =
                accounts.subList(from, to).stream().map(this::assetAccountView).toList();
        return new ChannelViews.Page<>(items, accounts.size(), page, size);
    }

    /** 查询账户金额汇总；未传花费时间时消耗金额按 0 汇总。 */
    public ChannelViews.AccountStatistics summarizeAccounts(AccountQuery query) {
        validateOptionalSpendDateRange(query);
        Aggregate value = accountQueryProvider.summarize(query);
        return new ChannelViews.AccountStatistics(
                money(value == null ? null : value.getOpeningBalance()),
                money(value == null ? null : value.getByBalance()),
                money(value == null ? null : value.getByBalanceU()),
                money(value == null ? null : value.getConsumption()),
                money(value == null ? null : value.getBalance()),
                money(value == null ? null : value.getActualDeduction()),
                platformAmountInDollars(value == null ? null : value.getAmountSpent()),
                money(value == null ? null : value.getRemainingSpendCap()));
    }

    /** 查询渠道账户状态数量。 */
    public ChannelViews.AccountCounts countAccountStatuses(Long channelId) {
        requireChannel(channelId);
        List<com.adpulse.main.adaccountasset.AdAccountAssetViews.Account> accounts =
                listChannelAssetAccounts(channelId);
        long activeCount =
                accounts.stream()
                        .filter(
                                account ->
                                        account.accountStatus() != null
                                                && List.of(1, 201)
                                                        .contains(account.accountStatus()))
                        .count();
        long closedCount =
                accounts.stream()
                        .filter(
                                account ->
                                        account.accountStatus() != null
                                                && List.of(2, 9, 100, 101, 202)
                                                        .contains(account.accountStatus()))
                        .count();
        long usingCount =
                accounts.stream().filter(account -> !account.assignments().isEmpty()).count();
        return new ChannelViews.AccountCounts(
                accounts.size(),
                activeCount,
                closedCount,
                accounts.size() - usingCount,
                usingCount,
                0,
                0,
                0);
    }

    /** 删除渠道账户。 */
    @Transactional
    public void deleteAccount(String accountId) {
        adAccountAssetService.detachChannel(accountId);
    }

    /** 批量分配账户给系统用户。 */
    @Transactional
    public void assignAccounts(ChannelRequests.AccountAssign request) {
        var pitcher = mapper.findPitcher(request.operatorId());
        if (pitcher == null) throw new ChannelException("投手不存在或已停用");
        adAccountAssetService.assign(
                new AssignmentSave(
                        request.accountIds(),
                        request.operatorId(),
                        pitcher.getNickName(),
                        true,
                        "MANUAL",
                        null));
    }

    /** 批量更新账户名称，逐项校验确保不会静默跳过不存在的账户。 */
    @Transactional
    public void updateAccountNames(List<ChannelRequests.AccountNameUpdate> requests) {
        throw new ChannelException("账户名称由fb_ad_accounts同步，不允许人工修改");
    }

    /** 批量更新账户归属渠道及类型。 */
    @Transactional
    public void updateAccountClassifications(List<ChannelRequests.AccountClassification> requests) {
        for (ChannelRequests.AccountClassification request : requests) {
            if (updateAccountClassification(request)) {
                adAccountAssetService.recordChannelStocked(
                        normalizeAccountId(request.accountId()),
                        AdAccountAssetService.UPDATE_SOURCE_CHANNEL_MANUAL);
            }
        }
    }

    /** 手动关联时，渠道、类型和投手必须在同一个事务内同时生效。 */
    @Transactional
    public void manualAssignAccounts(ChannelRequests.AccountManualAssignment request) {
        requireChannel(request.channelId());
        List<String> createdAccountIds = new ArrayList<>();
        for (ChannelRequests.AccountClassification account : request.accounts()) {
            if (!request.channelId().equals(account.channelId())) {
                throw new ChannelException("手动关联的账户渠道不一致");
            }
            if (updateAccountClassification(account)) {
                createdAccountIds.add(normalizeAccountId(account.accountId()));
            }
        }
        assignAccounts(
                new ChannelRequests.AccountAssign(
                        request.accounts().stream()
                                .map(ChannelRequests.AccountClassification::accountId)
                                .map(this::normalizeAccountId)
                                .toList(),
                        request.operatorId()));
        createdAccountIds.forEach(
                accountId ->
                        adAccountAssetService.recordChannelStocked(
                                accountId, AdAccountAssetService.UPDATE_SOURCE_CHANNEL_MANUAL));
    }

    private boolean updateAccountClassification(ChannelRequests.AccountClassification request) {
        String accountId = normalizeAccountId(request.accountId());
        Channel targetChannel = requireChannel(request.channelId());
        if (mapper.findAccountTypeByName(request.accountType()) == null) {
            throw new ChannelException("账户类型不存在：" + request.accountType());
        }
        return upsertChannelAsset(
                targetChannel,
                accountId,
                request.accountType(),
                AdAccountAssetService.UPDATE_SOURCE_CHANNEL_MANUAL);
    }

    /** 批量新增渠道账户。 */
    @Transactional
    public void batchCreateAccounts(AccountBatch request) {
        Channel targetChannel = requireChannel(request.channelId());
        var accountIds = new java.util.HashSet<String>();
        for (AccountImportItem item : request.accounts()) {
            String accountId = normalizeAccountId(item.accountId());
            if (accountId.isEmpty()) {
                throw new ChannelException("账户ID不能为空");
            }
            if (!accountIds.add(accountId)) {
                throw new ChannelException("账户列表中不允许有重复的账户ID：" + accountId);
            }
            if (mapper.findAccountTypeByName(item.accountType()) == null) {
                throw new ChannelException("账户类型不存在：" + item.accountType());
            }
            if (upsertChannelAsset(targetChannel, accountId, item.accountType())) {
                adAccountAssetService.recordChannelStocked(
                        accountId, AdAccountAssetService.UPDATE_SOURCE_CHANNEL_IMPORT);
            }
        }
    }

    /** 导入账户工作簿，返回逐行校验错误。 */
    @Transactional
    public List<String> importAccounts(byte[] content) {
        List<ChannelExcelCodec.ImportRow> rows = excelCodec.read(content);
        List<String> errors = new ArrayList<>();
        var fileAccountIds = new java.util.HashSet<String>();
        for (ChannelExcelCodec.ImportRow row : rows) {
            String error = validateImportRow(row, fileAccountIds);
            if (error != null) errors.add("第" + row.rowNumber() + "行：" + error);
        }
        if (!errors.isEmpty()) return errors;
        rows.forEach(
                row -> {
                    String accountId = normalizeAccountId(row.accountId());
                    if (upsertChannelAsset(
                            requireChannel(Long.valueOf(row.channelId())),
                            accountId,
                            row.accountType())) {
                        adAccountAssetService.recordChannelStocked(
                                accountId, AdAccountAssetService.UPDATE_SOURCE_CHANNEL_IMPORT);
                    }
                });
        return List.of();
    }

    private String validateImportRow(
            ChannelExcelCodec.ImportRow row, java.util.Set<String> fileAccountIds) {
        try {
            Long channelId = Long.valueOf(row.channelId());
            if (mapper.findChannel(channelId) == null) return "渠道不存在：" + row.channelId();
            if (row.accountId().isBlank()) return "账户ID不能为空";
            if (!fileAccountIds.add(row.accountId())) return "文件内账户ID重复：" + row.accountId();
            AdAccountAsset existing = adAccountAssetMapper.findByAccountId(row.accountId());
            if (existing != null
                    && existing.getChannelId() != null
                    && !channelId.equals(existing.getChannelId())) {
                return "账户已归属其他渠道：" + row.accountId();
            }
            if (mapper.findAccountTypeByName(row.accountType()) == null) {
                return "账户类型不存在：" + row.accountType();
            }
            if (row.status() < 1 || row.status() > 2) return "账户状态只能为1或2";
            if (row.usageStatus() < 0 || row.usageStatus() > 4) return "使用状态只能为0至4";
            return null;
        } catch (NumberFormatException exception) {
            return "渠道ID格式不正确";
        } catch (RuntimeException exception) {
            return exception.getMessage();
        }
    }

    /** 渠道导入只维护统一资产台账中的渠道归属和账户类型。 */
    private boolean upsertChannelAsset(Channel channel, String accountId, String accountType) {
        return upsertChannelAsset(
                channel,
                accountId,
                accountType,
                AdAccountAssetService.UPDATE_SOURCE_CHANNEL_IMPORT);
    }

    /** 渠道归属变更统一写入资产台账，来源用于区分导入和页面手动修改。 */
    private boolean upsertChannelAsset(
            Channel channel, String accountId, String accountType, String updateSource) {
        AdAccountAsset asset = adAccountAssetMapper.findByAccountId(accountId);
        Long operatorId = actorId();
        if (asset == null) {
            asset = new AdAccountAsset();
            asset.setAccountId(accountId);
            asset.setAccountName("");
            asset.setCreatedBy(operatorId);
        } else if (asset.getChannelId() != null && !channel.getId().equals(asset.getChannelId())) {
            throw new ChannelException(
                    "账户[" + accountId + "]已归属其他渠道[" + asset.getChannelName() + "]");
        }
        asset.setAccountType(accountType);
        asset.setChannelId(channel.getId());
        asset.setChannelName(channel.getChannelName());
        asset.setIsManuallyUpdated(true);
        asset.setManuallyUpdatedAt(java.time.LocalDateTime.now());
        asset.setManuallyUpdatedBy(operatorId);
        asset.setUpdateSource(updateSource);
        asset.setUpdatedBy(operatorId);
        return adAccountAssetService.upsertChannelAsset(asset);
    }

    /** 生成账户导入模板。 */
    public byte[] accountTemplate() {
        return excelCodec.template();
    }

    /** 导出查询到的全部账户。 */
    public byte[] exportAccounts(AccountQuery query) {
        AccountQuery exportQuery =
                new AccountQuery(
                        query.channelId(),
                        query.accountType(),
                        query.accountIds(),
                        query.bmId(),
                        query.subjectName(),
                        query.operatorName(),
                        query.belongTeamId(),
                        query.timezone(),
                        query.status(),
                        query.usageStatus(),
                        query.consumptionMin(),
                        query.consumptionMax(),
                        query.balanceMin(),
                        query.balanceMax(),
                        query.startDate(),
                        query.endDate(),
                        1,
                        1_000_000,
                        query.includeFields());
        return excelCodec.write(listAccounts(exportQuery).items());
    }

    /** 查询渠道上架信息。 */
    public ChannelViews.Goods getGoods(Long channelId) {
        requireChannel(channelId);
        Goods goods = mapper.findGoods(channelId);
        return goods == null ? null : goodsView(goods);
    }

    /** 保存渠道上架信息。 */
    @Transactional
    public ChannelViews.Goods saveGoods(Long channelId, GoodsSave request) {
        requireChannel(channelId);
        Goods goods = mapper.findGoods(channelId);
        boolean insert = goods == null;
        if (insert) {
            goods = new Goods();
            goods.setChannelId(channelId);
            goods.setPutawayStatus(0);
            goods.setCreatedBy(actorId());
        }
        goods.setGoodsName(request.goodsName());
        goods.setLaunchRegion(request.launchRegion());
        goods.setMinBuyLimit(request.minBuyLimit());
        goods.setRebateRate(request.rebateRate());
        goods.setRemark(request.remark());
        goods.setServiceFeeRatio(request.serviceFeeRatio());
        goods.setStockNum(request.stockNum());
        goods.setTimezone(request.timezone());
        goods.setUpdatedBy(actorId());
        if (insert) mapper.insertGoods(goods);
        else mapper.updateGoods(goods);
        return goodsView(Objects.requireNonNull(mapper.findGoods(channelId)));
    }

    /** 修改商品上下架状态。 */
    @Transactional
    public void setPutaway(Long channelId, Integer status) {
        if (status == null || status < 0 || status > 2) {
            throw new ChannelException("上下架状态不合法");
        }
        if (mapper.findGoods(channelId) == null) throw new ChannelException("请先维护上架信息");
        mapper.updateGoodsPutaway(channelId, status, actorId());
        mapper.updateChannelPutaway(channelId, status, actorId());
    }

    /** 分页查询账户广告系列花费。 */
    public ChannelViews.Page<ChannelViews.CampaignSpend> listCampaigns(
            String accountId,
            String campaignName,
            LocalDate startDate,
            LocalDate endDate,
            int page,
            int pageSize) {
        requireAccount(accountId);
        int safePage = safePage(page);
        int safeSize = safeSize(pageSize);
        var items =
                mapper
                        .findCampaigns(
                                accountId,
                                trimToNull(campaignName),
                                startDate,
                                endDate,
                                (safePage - 1) * safeSize,
                                safeSize)
                        .stream()
                        .map(
                                item ->
                                        new ChannelViews.CampaignSpend(
                                                item.getCampaignId(),
                                                item.getCampaignName(),
                                                money(item.getSpendAmount()),
                                                money(item.getReturnAmount())))
                        .toList();
        return new ChannelViews.Page<>(
                items,
                mapper.countCampaigns(accountId, trimToNull(campaignName), startDate, endDate),
                safePage,
                safeSize);
    }

    /** 查询可分配投手。 */
    public ChannelViews.Page<ChannelViews.Pitcher> listPitchers(
            String keyword, int page, int pageSize) {
        int safePage = safePage(page);
        int safeSize = safeSize(pageSize);
        var items =
                mapper
                        .findPitchers(trimToNull(keyword), (safePage - 1) * safeSize, safeSize)
                        .stream()
                        .map(
                                item ->
                                        new ChannelViews.Pitcher(
                                                stringId(item.getUserId()),
                                                item.getUserName(),
                                                item.getNickName()))
                        .toList();
        return new ChannelViews.Page<>(
                items, mapper.countPitchers(trimToNull(keyword)), safePage, safeSize);
    }

    /** 查询系统部门树。 */
    public List<ChannelViews.Department> departmentTree() {
        List<Department> departments = mapper.findDepartments();
        Map<Long, List<Department>> grouped = new HashMap<>();
        departments.forEach(
                item ->
                        grouped.computeIfAbsent(item.getParentId(), ignored -> new ArrayList<>())
                                .add(item));
        return buildDepartments(0L, grouped);
    }

    private List<ChannelViews.Department> buildDepartments(
            Long parentId, Map<Long, List<Department>> grouped) {
        return grouped.getOrDefault(parentId, List.of()).stream()
                .map(
                        item ->
                                new ChannelViews.Department(
                                        stringId(item.getId()),
                                        item.getLabel(),
                                        item.getStatus() == null || item.getStatus() != 1,
                                        buildDepartments(item.getId(), grouped)))
                .toList();
    }

    /** 渠道账户严格通过渠道 ID 关联，渠道名称只作为展示快照。 */
    private List<com.adpulse.main.adaccountasset.AdAccountAssetViews.Account>
            listChannelAssetAccounts(Long channelId) {
        List<String> accountIds = mapper.findAccountIdsByChannelId(channelId);
        return accountIds.isEmpty()
                ? List.of()
                : adAccountAssetService.listByAccountIds(accountIds);
    }

    private void enrichChannelBalances(
            List<Channel> channels, List<AccountChannel> accountChannels) {
        Map<Long, BigDecimal> balances = snapshotBalancesByChannel(accountChannels);
        channels.forEach(
                channel -> channel.setTotalBalance(balances.getOrDefault(channel.getId(), ZERO)));
    }

    private BigDecimal sumSnapshotBalances(List<AccountChannel> accountChannels) {
        return snapshotBalancesByChannel(accountChannels).values().stream()
                .reduce(ZERO, BigDecimal::add);
    }

    private Map<Long, BigDecimal> snapshotBalancesByChannel(List<AccountChannel> accountChannels) {
        if (accountChannels.isEmpty()) return Map.of();
        Map<String, AccountSnapshotProvider.AccountSnapshot> snapshots =
                accountSnapshotProvider.findByAccountIds(
                        accountChannels.stream()
                                .map(AccountChannel::getAccountId)
                                .distinct()
                                .toList());
        Map<Long, BigDecimal> balances = new HashMap<>();
        for (AccountChannel accountChannel : accountChannels) {
            AccountSnapshotProvider.AccountSnapshot snapshot =
                    snapshots.get(accountChannel.getAccountId());
            if (snapshot == null || snapshot.balance() == null) continue;
            balances.merge(accountChannel.getChannelId(), snapshot.balance(), BigDecimal::add);
        }
        return balances;
    }

    private String normalizeAccountId(String accountId) {
        return accountId.trim().replaceFirst("^act_", "");
    }

    private Channel requireChannel(Long id) {
        Channel channel = mapper.findChannel(id);
        if (channel == null) throw new ChannelException("渠道不存在");
        return channel;
    }

    private Account requireAccount(String id) {
        Account account = mapper.findAccount(id);
        if (account == null) throw new ChannelException("渠道账户不存在");
        return account;
    }

    private void validateRequiredChannel(ChannelSave value) {
        if (trimToNull(value.channelName()) == null
                || trimToNull(value.channelCode()) == null
                || value.channelType() == null
                || trimToNull(value.belongTeam()) == null
                || value.status() == null
                || trimToNull(value.settlementMethod()) == null
                || trimToNull(value.settlementCurrency()) == null
                || trimToNull(value.paymentAddress()) == null
                || trimToNull(value.loginUrl()) == null) {
            throw new ChannelException("渠道必填信息不完整");
        }
    }

    private void mergeChannel(Channel model, ChannelSave value) {
        if (value.channelName() != null) model.setChannelName(value.channelName().trim());
        if (value.channelShortName() != null)
            model.setChannelShortName(value.channelShortName().trim());
        if (value.channelCode() != null) model.setChannelCode(value.channelCode().trim());
        if (value.channelType() != null) model.setChannelType(value.channelType());
        if (value.belongTeam() != null) model.setBelongTeam(value.belongTeam());
        if (value.status() != null) model.setStatus(value.status());
        if (value.settlementMethod() != null) model.setSettlementMethod(value.settlementMethod());
        if (value.settlementCurrency() != null)
            model.setSettlementCurrency(value.settlementCurrency());
        if (value.buyoutAmount() != null) model.setBuyoutAmount(value.buyoutAmount());
        if (value.rechargeAmount() != null) model.setRechargeAmount(value.rechargeAmount());
        if (value.paymentAddress() != null) model.setPaymentAddress(value.paymentAddress());
        if (value.loginUrl() != null) model.setLoginUrl(value.loginUrl());
        if (value.remark() != null) model.setRemark(value.remark());
        if (value.tgGroupId() != null) model.setTgGroupId(value.tgGroupId());
        if (value.tgGroupName() != null) model.setTgGroupName(value.tgGroupName());
    }

    private void validateRate(Long channelId, Long excludedId, RateSave request) {
        if (request.expiryDate() != null
                && request.expiryDate().isBefore(request.effectiveDate())) {
            throw new ChannelException("失效日期不能早于生效日期");
        }
        if (mapper.countRateOverlaps(
                        channelId, excludedId, request.effectiveDate(), request.expiryDate())
                > 0) {
            throw new ChannelException("费率生效区间与已有记录重叠");
        }
    }

    private void applyRate(Rate rate, RateSave request) {
        rate.setServiceFee(request.serviceFee());
        rate.setRebateRate(request.rebateRate());
        rate.setEffectiveDate(request.effectiveDate());
        rate.setExpiryDate(request.expiryDate());
        LocalDate today = LocalDate.now();
        rate.setStatus(
                !today.isBefore(request.effectiveDate())
                                && (request.expiryDate() == null
                                        || !today.isAfter(request.expiryDate()))
                        ? 1
                        : 0);
    }

    private ChannelViews.ChannelDetail channelView(Channel item) {
        return new ChannelViews.ChannelDetail(
                stringId(item.getId()),
                item.getChannelName(),
                item.getChannelShortName(),
                item.getChannelCode(),
                item.getChannelType(),
                item.getBelongTeam(),
                item.getStatus(),
                item.getPutawayStatus(),
                item.getSettlementMethod(),
                item.getSettlementCurrency(),
                money(item.getBuyoutAmount()),
                money(item.getRechargeAmount()),
                item.getPaymentAddress(),
                item.getLoginUrl(),
                item.getRemark(),
                item.getTgGroupId(),
                item.getTgGroupName(),
                money(item.getServiceFee()),
                money(item.getRebateRate()),
                money(item.getTotalConsumption()),
                money(item.getTotalBalance()),
                money(item.getActivationFee()),
                money(item.getTotalByBalance()),
                money(item.getTotalByBalanceU()),
                item.getUsageStatus(),
                item.getCreatedAt(),
                item.getUpdatedAt());
    }

    private ChannelViews.Rate rateView(Rate item) {
        return new ChannelViews.Rate(
                stringId(item.getId()),
                stringId(item.getChannelId()),
                item.getServiceFee(),
                item.getRebateRate(),
                item.getEffectiveDate(),
                item.getExpiryDate(),
                item.getStatus(),
                item.getCreatedAt(),
                item.getUpdatedAt());
    }

    private ChannelViews.AccountType accountTypeView(AccountType item) {
        return new ChannelViews.AccountType(
                stringId(item.getId()), item.getAccountType(), item.getCreatedAt());
    }

    private ChannelViews.Account accountView(Account item) {
        return new ChannelViews.Account(
                stringId(item.getChannelId()),
                item.getAccountId(),
                item.getAccountName(),
                item.getAccountType(),
                item.getFbAccountId(),
                item.getTakeTime(),
                item.getTimezone(),
                item.getBmId(),
                item.getBmFromFeishu(),
                money(item.getOpeningBalance()),
                money(item.getByBalance()),
                money(item.getByBalanceU()),
                money(item.getConsumption()),
                money(item.getBalance()),
                money(item.getActualDeduction()),
                platformAmountInDollars(item.getAmountSpent()),
                money(item.getRemainingSpendCap()),
                item.getStatus(),
                item.isSynced(),
                item.getUsageStatus(),
                item.getSubjectName(),
                stringId(item.getOperatorId()),
                item.getOperatorName(),
                item.getBelongTeam(),
                stringId(item.getBelongTeamId()),
                item.getOpenDate(),
                item.getCreatedAt(),
                item.getAssignTime(),
                item.getRemark());
    }

    private ChannelViews.Account assetAccountView(
            com.adpulse.main.adaccountasset.AdAccountAssetViews.Account item) {
        Integer timezone;
        try {
            timezone = item.timezone().isBlank() ? null : Integer.valueOf(item.timezone());
        } catch (NumberFormatException ignored) {
            timezone = null;
        }
        return new ChannelViews.Account(
                item.channelId(),
                item.accountId(),
                item.accountName(),
                item.accountType(),
                item.accountId(),
                null,
                timezone,
                item.managedBmId(),
                item.managedBm(),
                ZERO,
                ZERO,
                ZERO,
                ZERO,
                ZERO,
                ZERO,
                ZERO,
                ZERO,
                item.accountStatus(),
                !"PLATFORM_MISSING".equals(item.syncStatus()),
                item.assignments().isEmpty() ? 0 : 1,
                null,
                item.usageUserId(),
                item.usageUserName(),
                item.usageDepartmentName(),
                null,
                null,
                null,
                null,
                null);
    }

    private void enrichAccountSnapshots(List<Account> accounts) {
        Map<String, AccountSnapshotProvider.AccountSnapshot> snapshots =
                accountSnapshotProvider.findByAccountIds(
                        accounts.stream().map(Account::getAccountId).toList());
        for (Account account : accounts) {
            AccountSnapshotProvider.AccountSnapshot snapshot =
                    snapshots.get(account.getAccountId());
            if (snapshot == null) continue;
            account.setSynced(true);
            if (snapshot.accountName() != null) account.setAccountName(snapshot.accountName());
            if (snapshot.status() != null) account.setStatus(snapshot.status());
            if (snapshot.takeTime() != null) account.setTakeTime(snapshot.takeTime());
            if (snapshot.timezone() != null) account.setTimezone(snapshot.timezone());
            if (snapshot.bmId() != null) account.setBmId(snapshot.bmId());
            if (snapshot.balance() != null) account.setBalance(snapshot.balance());
            if (snapshot.amountSpent() != null) account.setAmountSpent(snapshot.amountSpent());
            if (snapshot.remainingSpendCap() != null) {
                account.setRemainingSpendCap(snapshot.remainingSpendCap());
            }
            if (snapshot.subjectName() != null) account.setSubjectName(snapshot.subjectName());
        }
    }

    private void validateSpendDateRange(AccountQuery query) {
        if (query.startDate() == null || query.endDate() == null) {
            throw new ChannelException("请选择消耗/花费时间");
        }
        if (query.startDate().isAfter(query.endDate())) {
            throw new ChannelException("消耗/花费开始时间不能晚于结束时间");
        }
    }

    /** 花费筛选需要完整日期区间，基础账户列表查询则不依赖花费数据。 */
    private void validateOptionalSpendDateRange(AccountQuery query) {
        boolean hasStartDate = query.startDate() != null;
        boolean hasEndDate = query.endDate() != null;
        if (!hasStartDate && !hasEndDate) {
            if (query.consumptionMin() != null || query.consumptionMax() != null) {
                throw new ChannelException("筛选消耗/花费区间时请选择完整时间");
            }
            return;
        }
        validateSpendDateRange(query);
    }

    private ChannelViews.Goods goodsView(Goods item) {
        return new ChannelViews.Goods(
                stringId(item.getChannelId()),
                item.getGoodsName(),
                item.getLaunchRegion(),
                item.getMinBuyLimit(),
                item.getRebateRate(),
                item.getRemark(),
                item.getServiceFeeRatio(),
                item.getStockNum(),
                item.getTimezone(),
                item.getPutawayStatus());
    }

    private int safePage(Integer value) {
        return Math.max(1, value == null ? 1 : value);
    }

    private int safeSize(Integer value) {
        return Math.min(1_000_000, Math.max(1, value == null ? 20 : value));
    }

    private long longValue(Long value) {
        return value == null ? 0L : value;
    }

    private BigDecimal money(BigDecimal value) {
        return value == null ? ZERO : value;
    }

    /** Facebook 账户快照中的累计花费以分保存，对外展示时转换为美元。 */
    private BigDecimal platformAmountInDollars(BigDecimal value) {
        return money(value).movePointLeft(2);
    }

    private String stringId(Long value) {
        return value == null ? null : value.toString();
    }

    private String trimToNull(String value) {
        if (value == null || value.isBlank()) return null;
        return value.trim();
    }

    private Long actorId() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        throw new ChannelException("登录状态无效");
    }

    /** 可直接展示的渠道业务异常。 */
    public static class ChannelException extends RuntimeException {
        public ChannelException(String message) {
            super(message);
        }

        public ChannelException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
