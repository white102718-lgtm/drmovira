package com.adpulse.main.cardstation.service;

import com.adpulse.main.cardstation.dto.CardStationRequests.AutoAdjustSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.CardQuery;
import com.adpulse.main.cardstation.dto.CardStationRequests.LimitRuleSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.LimitSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.StatusSave;
import com.adpulse.main.cardstation.dto.CardStationViews;
import com.adpulse.main.cardstation.mapper.CardStationMapper;
import com.adpulse.main.cardstation.model.CardStationModels.Card;
import com.adpulse.main.cardstation.model.CardStationModels.LimitRule;
import com.adpulse.main.cardstation.model.CardStationModels.Statistics;
import com.adpulse.system.common.security.CurrentUser;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.util.List;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** PhotonPay与ArrivalX卡台管理服务。 */
@Service
public class CardStationService {
    private final CardStationMapper mapper;

    public CardStationService(CardStationMapper mapper) {
        this.mapper = mapper;
    }

    /** 分页查询指定平台卡片。 */
    public CardStationViews.Page<CardStationViews.Card> cards(CardQuery query) {
        validatePlatform(query.platform());
        int page = Math.max(1, query.page() == null ? 1 : query.page());
        int pageSize = Math.min(500, Math.max(1, query.pageSize() == null ? 20 : query.pageSize()));
        List<CardStationViews.Card> items =
                mapper.findCards(query, (page - 1) * pageSize, pageSize).stream()
                        .map(this::view)
                        .toList();
        return new CardStationViews.Page<>(items, mapper.countCards(query), page, pageSize);
    }

    /** 查询单张卡片详情。 */
    public CardStationViews.Card detail(String platform, String cardId) {
        validatePlatform(platform);
        return view(requireCard(platform, cardId));
    }

    /** 查询卡台账户余额。 */
    public List<CardStationViews.Balance> balances(String platform) {
        validatePlatform(platform);
        return mapper.findBalances(platform).stream()
                .map(
                        item ->
                                new CardStationViews.Balance(
                                        item.getProductCode(),
                                        item.getCurrency(),
                                        money(item.getBalance()),
                                        money(item.getFrozenBalance())))
                .toList();
    }

    /** 查询卡片状态与余额统计。 */
    public CardStationViews.Statistics statistics(String platform) {
        validatePlatform(platform);
        Statistics item = mapper.summarize(platform);
        return new CardStationViews.Statistics(
                number(item == null ? null : item.getTotal()),
                number(item == null ? null : item.getActive()),
                number(item == null ? null : item.getFrozen()),
                money(item == null ? null : item.getBalance()));
    }

    /** 查询PhotonPay与ArrivalX共用的卡日授权额度规则。 */
    public CardStationViews.LimitRule limitRule() {
        LimitRule item = mapper.findLimitRule();
        if (item == null)
            return new CardStationViews.LimitRule(false, null, null, null, false, null);
        return limitRuleView(item);
    }

    /** 原子保存PhotonPay与ArrivalX共用的卡日授权额度规则。 */
    @Transactional
    public CardStationViews.LimitRule saveLimitRule(LimitRuleSave request) {
        mapper.upsertLimitRule(
                request.dailyPeriod(),
                request.adjustAmount(),
                request.minAmount(),
                request.autoAdjustEnabled(),
                actorId());
        return limitRule();
    }

    /** 修改卡日授权额度规则的自动调整开关。 */
    @Transactional
    public CardStationViews.LimitRule updateLimitRuleAutoAdjust(AutoAdjustSave request) {
        LimitRule item = mapper.findLimitRule();
        if (item == null) throw new CardStationException("请先保存限额规则，再开启自动调整");
        int updated = mapper.updateLimitRuleAutoAdjust(item.getId(), request.enabled(), actorId());
        if (updated != 1) throw new CardStationException("限额规则已变化，请刷新后重试");
        return limitRule();
    }

    /** 将第三方全量同步请求写入新服务任务队列。 */
    @Transactional
    public CardStationViews.SyncJob enqueueSync(String platform) {
        validatePlatform(platform);
        mapper.insertSyncJob(platform, "FULL_SYNC", null, "{}", actorId());
        return new CardStationViews.SyncJob(mapper.lastInsertId().toString(), platform, 0);
    }

    /** 批量保存限额并写入待执行队列。 */
    @Transactional
    public void updateLimits(String platform, LimitSave request) {
        validatePlatform(platform);
        for (String cardId : request.cardIds()) {
            Card card = requireCard(platform, cardId);
            mapper.insertLimitRecord(
                    platform,
                    cardId,
                    card.getUtilizationLimitAmount(),
                    request.limitAmount(),
                    request.preset(),
                    actorId());
            mapper.updateLimit(platform, cardId, request.limitAmount(), request.preset());
            mapper.insertSyncJob(platform, "LIMIT_UPDATE", cardId, "{}", actorId());
        }
    }

    /** 批量冻结或解冻PhotonPay卡片并写入待执行队列。 */
    @Transactional
    public void updateStatuses(String platform, StatusSave request) {
        validatePlatform(platform);
        String normalized = normalizeStatus(request.status());
        for (String cardId : request.ids()) {
            requireCard(platform, cardId);
            mapper.updateStatus(platform, cardId, normalized);
            mapper.insertSyncJob(platform, "STATUS_UPDATE", cardId, "{}", actorId());
        }
    }

    /** 分页查询卡片限额调整记录。 */
    public CardStationViews.Page<CardStationViews.LimitRecord> limitRecords(
            String platform, String cardId, Integer pageValue, Integer pageSizeValue) {
        validatePlatform(platform);
        int page = Math.max(1, pageValue == null ? 1 : pageValue);
        int pageSize = Math.min(500, Math.max(1, pageSizeValue == null ? 20 : pageSizeValue));
        var items =
                mapper.findLimitRecords(platform, cardId, (page - 1) * pageSize, pageSize).stream()
                        .map(
                                item ->
                                        new CardStationViews.LimitRecord(
                                                item.getId().toString(),
                                                item.getExternalCardId(),
                                                item.getOldAmount(),
                                                item.getNewAmount(),
                                                item.getPreset(),
                                                item.getStatus(),
                                                item.getErrorMessage(),
                                                item.getCreatedAt()))
                        .toList();
        return new CardStationViews.Page<>(
                items, mapper.countLimitRecords(platform, cardId), page, pageSize);
    }

    /** 导出当前筛选条件下的卡片。 */
    public byte[] export(CardQuery query) {
        validatePlatform(query.platform());
        try (var workbook = new XSSFWorkbook();
                var output = new ByteArrayOutputStream()) {
            var sheet = workbook.createSheet("卡片列表");
            var header = sheet.createRow(0);
            List<String> headers = List.of("卡片ID", "卡片名称", "脱敏卡号", "状态", "余额", "币种", "广告账户");
            for (int index = 0; index < headers.size(); index++)
                header.createCell(index).setCellValue(headers.get(index));
            List<Card> cards = mapper.findCards(query, 0, 1_000_000);
            for (int index = 0; index < cards.size(); index++) {
                Card item = cards.get(index);
                var row = sheet.createRow(index + 1);
                List<String> values =
                        List.of(
                                text(item.getExternalCardId()),
                                text(item.getCardName()),
                                text(item.getMaskedPan()),
                                text(item.getCardStatus()),
                                text(item.getBalance()),
                                text(item.getCurrency()),
                                text(item.getAdvertisementAccountId()));
                for (int cell = 0; cell < values.size(); cell++)
                    row.createCell(cell).setCellValue(values.get(cell));
            }
            workbook.write(output);
            return output.toByteArray();
        } catch (IOException exception) {
            throw new CardStationException("卡片导出失败");
        }
    }

    private CardStationViews.Card view(Card item) {
        String status = item.getCardStatus();
        return new CardStationViews.Card(
                item.getExternalCardId(),
                item.getExternalCardId(),
                item.getCardName(),
                item.getCardName(),
                item.getMaskedPan(),
                item.getMaskedPan(),
                status,
                status == null ? null : status.toUpperCase(),
                money(item.getBalance()),
                money(item.getBalance()),
                item.getCurrency(),
                item.getCurrency(),
                item.getAdvertisementAccountId(),
                item.getCompanyEntity(),
                item.getDailyLimit(),
                item.getMonthlyLimit(),
                item.getTransactionMinAmount(),
                item.getTransactionMaxAmount(),
                item.getUtilizationLimitAmount(),
                item.getUtilizationLimitPreset(),
                item.getPeriodMaxConsumeAmount(),
                item.getProviderCreatedAt() == null
                        ? item.getCreatedAt()
                        : item.getProviderCreatedAt(),
                item.getProviderUpdatedAt() == null
                        ? item.getUpdatedAt()
                        : item.getProviderUpdatedAt());
    }

    private CardStationViews.LimitRule limitRuleView(LimitRule item) {
        return new CardStationViews.LimitRule(
                true,
                item.getDailyPeriod(),
                item.getAdjustAmount(),
                item.getMinAmount(),
                Boolean.TRUE.equals(item.getAutoAdjustEnabled()),
                item.getUpdatedAt());
    }

    private Card requireCard(String platform, String cardId) {
        Card card = mapper.findCard(platform, cardId);
        if (card == null) throw new CardStationException("卡片不存在");
        return card;
    }

    private void validatePlatform(String platform) {
        if (!"photonpay".equals(platform) && !"arrivalx".equals(platform))
            throw new CardStationException("不支持的卡台平台");
    }

    private String normalizeStatus(String status) {
        if ("freeze".equalsIgnoreCase(status)) return "frozen";
        if ("unfreeze".equalsIgnoreCase(status)) return "active";
        throw new CardStationException("仅支持冻结或解冻操作");
    }

    private long number(Long value) {
        return value == null ? 0 : value;
    }

    private BigDecimal money(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    private Long actorId() {
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (principal instanceof CurrentUser currentUser) return currentUser.userId();
        throw new CardStationException("登录状态无效");
    }

    /** 可直接展示的卡台业务异常。 */
    public static class CardStationException extends RuntimeException {
        /** 创建卡台业务异常。 */
        public CardStationException(String message) {
            super(message);
        }
    }
}
