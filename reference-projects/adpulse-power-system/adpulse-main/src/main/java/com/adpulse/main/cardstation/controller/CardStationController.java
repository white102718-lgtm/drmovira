package com.adpulse.main.cardstation.controller;

import com.adpulse.main.cardstation.dto.CardStationRequests.AutoAdjustSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.CardQuery;
import com.adpulse.main.cardstation.dto.CardStationRequests.LimitRuleSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.LimitSave;
import com.adpulse.main.cardstation.dto.CardStationRequests.StatusSave;
import com.adpulse.main.cardstation.dto.CardStationViews;
import com.adpulse.main.cardstation.service.CardStationService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** PhotonPay与ArrivalX卡台管理接口。 */
@RestController
@RequestMapping("/card-station")
public class CardStationController {
    private final CardStationService service;

    public CardStationController(CardStationService service) {
        this.service = service;
    }

    /** 分页查询卡片。 */
    @GetMapping("/cards")
    public ApiResponse<CardStationViews.Page<CardStationViews.Card>> cards(CardQuery query) {
        return ApiResponse.success(service.cards(query));
    }

    /** 查询卡台余额。 */
    @GetMapping("/balances")
    public ApiResponse<List<CardStationViews.Balance>> balances(@RequestParam String platform) {
        return ApiResponse.success(service.balances(platform));
    }

    /** 查询卡台统计。 */
    @GetMapping("/statistics")
    public ApiResponse<CardStationViews.Statistics> statistics(@RequestParam String platform) {
        return ApiResponse.success(service.statistics(platform));
    }

    /** 查询PhotonPay与ArrivalX共用的卡日授权额度规则。 */
    @GetMapping("/limit-rule")
    public ApiResponse<CardStationViews.LimitRule> limitRule() {
        return ApiResponse.success(service.limitRule());
    }

    /** 保存PhotonPay与ArrivalX共用的卡日授权额度规则。 */
    @PutMapping("/limit-rule")
    public ApiResponse<CardStationViews.LimitRule> saveLimitRule(
            @Valid @RequestBody LimitRuleSave request) {
        return ApiResponse.success(service.saveLimitRule(request));
    }

    /** 修改卡日授权额度规则的自动调整开关。 */
    @PatchMapping("/limit-rule/auto-adjust")
    public ApiResponse<CardStationViews.LimitRule> updateLimitRuleAutoAdjust(
            @Valid @RequestBody AutoAdjustSave request) {
        return ApiResponse.success(service.updateLimitRuleAutoAdjust(request));
    }

    /** 创建第三方全量同步任务。 */
    @PostMapping("/{platform}/sync")
    public ApiResponse<CardStationViews.SyncJob> sync(@PathVariable String platform) {
        return ApiResponse.success(service.enqueueSync(platform));
    }

    /** 查询卡片详情。 */
    @GetMapping("/{platform}/cards/{cardId}")
    public ApiResponse<CardStationViews.Card> detail(
            @PathVariable String platform, @PathVariable String cardId) {
        return ApiResponse.success(service.detail(platform, cardId));
    }

    /** 批量调整卡片限额。 */
    @PostMapping("/{platform}/limits")
    public ApiResponse<Void> limits(
            @PathVariable String platform, @Valid @RequestBody LimitSave request) {
        service.updateLimits(platform, request);
        return ApiResponse.success();
    }

    /** 批量冻结或解冻卡片。 */
    @PatchMapping("/{platform}/status")
    public ApiResponse<Void> statuses(
            @PathVariable String platform, @Valid @RequestBody StatusSave request) {
        service.updateStatuses(platform, request);
        return ApiResponse.success();
    }

    /** 分页查询限额调整记录。 */
    @GetMapping("/limit-records")
    public ApiResponse<CardStationViews.Page<CardStationViews.LimitRecord>> limitRecords(
            @RequestParam String platform,
            @RequestParam String cardId,
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer pageSize) {
        return ApiResponse.success(service.limitRecords(platform, cardId, page, pageSize));
    }

    /** 导出当前筛选条件下的卡片。 */
    @PostMapping("/cards/export")
    public ResponseEntity<byte[]> export(CardQuery query) {
        byte[] content = service.export(query);
        ContentDisposition disposition =
                ContentDisposition.attachment()
                        .filename("卡台卡片.xlsx", StandardCharsets.UTF_8)
                        .build();
        return ResponseEntity.ok()
                .contentType(
                        MediaType.parseMediaType(
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .contentLength(content.length)
                .body(content);
    }
}
