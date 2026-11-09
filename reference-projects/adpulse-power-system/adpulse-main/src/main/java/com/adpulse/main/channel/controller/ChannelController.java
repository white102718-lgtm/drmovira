package com.adpulse.main.channel.controller;

import com.adpulse.main.channel.dto.ChannelRequests;
import com.adpulse.main.channel.dto.ChannelRequests.AccountBatch;
import com.adpulse.main.channel.dto.ChannelRequests.AccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.AccountTypeSave;
import com.adpulse.main.channel.dto.ChannelRequests.AvailableAccountQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelPeriodSpendQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelQuery;
import com.adpulse.main.channel.dto.ChannelRequests.ChannelSave;
import com.adpulse.main.channel.dto.ChannelRequests.GoodsSave;
import com.adpulse.main.channel.dto.ChannelRequests.PutawaySave;
import com.adpulse.main.channel.dto.ChannelRequests.RateSave;
import com.adpulse.main.channel.dto.ChannelViews;
import com.adpulse.main.channel.service.ChannelPeriodSpendService;
import com.adpulse.main.channel.service.ChannelService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 渠道管理、渠道详情及关联账户接口。 */
@RestController
@RequestMapping
public class ChannelController {
    private static final MediaType XLSX =
            MediaType.parseMediaType(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    private final ChannelService service;
    private final ChannelPeriodSpendService periodSpendService;

    public ChannelController(ChannelService service, ChannelPeriodSpendService periodSpendService) {
        this.service = service;
        this.periodSpendService = periodSpendService;
    }

    /** 分页查询渠道。 */
    @GetMapping("/channels")
    public ApiResponse<ChannelViews.Page<ChannelViews.ChannelDetail>> list(ChannelQuery query) {
        return ApiResponse.success(service.listChannels(query));
    }

    /** 查询渠道汇总。 */
    @GetMapping("/channels/summary")
    public ApiResponse<ChannelViews.ChannelSummary> summary(ChannelQuery query) {
        return ApiResponse.success(service.summarizeChannels(query));
    }

    /** 查询与广告面板渠道 Tab 同口径的周期花费。 */
    @GetMapping("/channels/period-spend")
    public ApiResponse<ChannelViews.ChannelPeriodSpend> periodSpend(
            @Valid ChannelPeriodSpendQuery query) {
        return ApiResponse.success(periodSpendService.query(query));
    }

    /** 查询账户类型维度的渠道汇总。 */
    @GetMapping("/channels/type-summary")
    public ApiResponse<ChannelViews.Page<ChannelViews.ChannelTypeSummary>> typeSummary(
            ChannelQuery query) {
        return ApiResponse.success(service.listTypeSummaries(query));
    }

    /** 查询渠道详情。 */
    @GetMapping("/channels/{id}")
    public ApiResponse<ChannelViews.ChannelDetail> get(@PathVariable Long id) {
        return ApiResponse.success(service.getChannel(id));
    }

    /** 查询打款申请的渠道昨日消耗和收款地址。 */
    @GetMapping("/channels/{id}/payment-context")
    public ApiResponse<ChannelViews.ChannelPaymentContext> paymentContext(@PathVariable Long id) {
        return ApiResponse.success(service.getPaymentContext(id));
    }

    /** 创建渠道。 */
    @PostMapping("/channels")
    public ApiResponse<ChannelViews.ChannelDetail> create(@Valid @RequestBody ChannelSave request) {
        return ApiResponse.success(service.createChannel(request));
    }

    /** 增量修改渠道。 */
    @PatchMapping("/channels/{id}")
    public ApiResponse<ChannelViews.ChannelDetail> update(
            @PathVariable Long id, @Valid @RequestBody ChannelSave request) {
        return ApiResponse.success(service.updateChannel(id, request));
    }

    /** 删除渠道。 */
    @DeleteMapping("/channels/{id}")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.deleteChannel(id);
        return ApiResponse.success();
    }

    /** 分页查询渠道费率。 */
    @GetMapping("/channels/{channelId}/rates")
    public ApiResponse<ChannelViews.Page<ChannelViews.Rate>> rates(
            @PathVariable Long channelId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.listRates(channelId, page, pageSize));
    }

    /** 创建渠道费率。 */
    @PostMapping("/channels/{channelId}/rates")
    public ApiResponse<ChannelViews.Rate> createRate(
            @PathVariable Long channelId, @Valid @RequestBody RateSave request) {
        return ApiResponse.success(service.createRate(channelId, request));
    }

    /** 修改渠道费率。 */
    @PutMapping("/channels/{channelId}/rates/{rateId}")
    public ApiResponse<ChannelViews.Rate> updateRate(
            @PathVariable Long channelId,
            @PathVariable Long rateId,
            @Valid @RequestBody RateSave request) {
        return ApiResponse.success(service.updateRate(channelId, rateId, request));
    }

    /** 查询账户类型。 */
    @GetMapping("/channel-account-types")
    public ApiResponse<List<ChannelViews.AccountType>> accountTypes() {
        return ApiResponse.success(service.listAccountTypes());
    }

    /** 创建账户类型。 */
    @PostMapping("/channel-account-types")
    public ApiResponse<ChannelViews.AccountType> createAccountType(
            @Valid @RequestBody AccountTypeSave request) {
        return ApiResponse.success(service.createAccountType(request));
    }

    /** 删除账户类型。 */
    @DeleteMapping("/channel-account-types/{id}")
    public ApiResponse<Void> deleteAccountType(@PathVariable Long id) {
        service.deleteAccountType(id);
        return ApiResponse.success();
    }

    /** 分页查询关联账户。 */
    @PostMapping("/channel-accounts/search")
    public ApiResponse<ChannelViews.Page<ChannelViews.Account>> accounts(
            @RequestBody AccountQuery request) {
        return ApiResponse.success(service.listAccounts(request));
    }

    /** 分页查询广告户申请办理账户，无需提供花费时间。 */
    @PostMapping("/channel-accounts/available/search")
    public ApiResponse<ChannelViews.Page<ChannelViews.Account>> availableAccounts(
            @Valid @RequestBody AvailableAccountQuery request) {
        return ApiResponse.success(service.listAvailableAccounts(request));
    }

    /** 查询关联账户金额汇总。 */
    @PostMapping("/channel-accounts/statistics")
    public ApiResponse<ChannelViews.AccountStatistics> accountStatistics(
            @RequestBody AccountQuery request) {
        return ApiResponse.success(service.summarizeAccounts(request));
    }

    /** 查询渠道账户状态数量。 */
    @GetMapping("/channels/{channelId}/account-counts")
    public ApiResponse<ChannelViews.AccountCounts> accountCounts(@PathVariable Long channelId) {
        return ApiResponse.success(service.countAccountStatuses(channelId));
    }

    /** 删除渠道账户。 */
    @DeleteMapping("/channel-accounts/{accountId}")
    public ApiResponse<Void> deleteAccount(@PathVariable String accountId) {
        service.deleteAccount(accountId);
        return ApiResponse.success();
    }

    /** 批量分配投手。 */
    @PatchMapping("/channel-accounts/assignment")
    public ApiResponse<Void> assign(@Valid @RequestBody ChannelRequests.AccountAssign request) {
        service.assignAccounts(request);
        return ApiResponse.success();
    }

    /** 批量更新广告账户展示名称。 */
    @PatchMapping("/channel-accounts/names")
    public ApiResponse<Void> updateAccountNames(
            @Valid @RequestBody List<ChannelRequests.AccountNameUpdate> request) {
        service.updateAccountNames(request);
        return ApiResponse.success();
    }

    /** 批量修改广告账户渠道及类型归类。 */
    @PatchMapping("/channel-accounts/classifications")
    public ApiResponse<Void> updateAccountClassifications(
            @Valid @RequestBody List<ChannelRequests.AccountClassification> request) {
        service.updateAccountClassifications(request);
        return ApiResponse.success();
    }

    /** 手动建立广告账户、渠道和投手关系。 */
    @PatchMapping("/channel-accounts/manual-assignment")
    public ApiResponse<Void> manualAssign(
            @Valid @RequestBody ChannelRequests.AccountManualAssignment request) {
        service.manualAssignAccounts(request);
        return ApiResponse.success();
    }

    /** 批量创建渠道账户。 */
    @PostMapping("/channels/{channelId}/accounts/batch")
    public ApiResponse<Void> batchCreate(
            @PathVariable Long channelId, @Valid @RequestBody AccountBatch request) {
        if (!channelId.equals(request.channelId())) {
            throw new ChannelService.ChannelException("路径渠道与请求渠道不一致");
        }
        service.batchCreateAccounts(request);
        return ApiResponse.success();
    }

    /** 导入渠道账户。 */
    @PostMapping(value = "/channel-accounts/import", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<List<String>> importAccounts(@RequestPart("file") MultipartFile file)
            throws java.io.IOException {
        if (file.isEmpty()) throw new ChannelService.ChannelException("请选择导入文件");
        if (file.getSize() > 5L * 1024 * 1024) {
            throw new ChannelService.ChannelException("导入文件不能超过5MB");
        }
        return ApiResponse.success(service.importAccounts(file.getBytes()));
    }

    /** 下载渠道账户导入模板。 */
    @GetMapping("/channel-accounts/import-template")
    public ResponseEntity<byte[]> template() {
        return download(service.accountTemplate(), "渠道账户导入模板.xlsx");
    }

    /** 导出渠道账户。 */
    @PostMapping("/channel-accounts/export")
    public ResponseEntity<byte[]> export(@RequestBody AccountQuery request) {
        return download(service.exportAccounts(request), "渠道账户数据.xlsx");
    }

    /** 查询渠道上架信息。 */
    @GetMapping("/channels/{channelId}/goods")
    public ApiResponse<ChannelViews.Goods> goods(@PathVariable Long channelId) {
        return ApiResponse.success(service.getGoods(channelId));
    }

    /** 保存渠道上架信息。 */
    @PutMapping("/channels/{channelId}/goods")
    public ApiResponse<ChannelViews.Goods> saveGoods(
            @PathVariable Long channelId, @Valid @RequestBody GoodsSave request) {
        return ApiResponse.success(service.saveGoods(channelId, request));
    }

    /** 修改渠道上下架状态。 */
    @PatchMapping("/channels/{channelId}/goods/putaway")
    public ApiResponse<Void> putaway(
            @PathVariable Long channelId, @Valid @RequestBody PutawaySave request) {
        service.setPutaway(channelId, request.putawayStatus());
        return ApiResponse.success();
    }

    /** 查询账户广告系列花费。 */
    @GetMapping("/channel-accounts/{accountId}/campaigns")
    public ApiResponse<ChannelViews.Page<ChannelViews.CampaignSpend>> campaigns(
            @PathVariable String accountId,
            @RequestParam(required = false) String campaignName,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate startDate,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                    LocalDate endDate,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(
                service.listCampaigns(accountId, campaignName, startDate, endDate, page, pageSize));
    }

    /** 查询可分配投手。 */
    @GetMapping("/channel-support/pitchers")
    public ApiResponse<ChannelViews.Page<ChannelViews.Pitcher>> pitchers(
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.listPitchers(keyword, page, pageSize));
    }

    /** 查询系统部门树。 */
    @GetMapping("/channel-support/departments")
    public ApiResponse<List<ChannelViews.Department>> departments() {
        return ApiResponse.success(service.departmentTree());
    }

    private ResponseEntity<byte[]> download(byte[] content, String fileName) {
        ContentDisposition disposition =
                ContentDisposition.attachment().filename(fileName, StandardCharsets.UTF_8).build();
        return ResponseEntity.ok()
                .contentType(XLSX)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .contentLength(content.length)
                .body(content);
    }
}
