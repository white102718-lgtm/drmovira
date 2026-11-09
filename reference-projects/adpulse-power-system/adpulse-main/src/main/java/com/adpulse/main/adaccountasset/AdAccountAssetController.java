package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AccountAttributeSave;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AccountBatchQuery;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AccountSearch;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentReplace;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.AssignmentSave;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.BatchUpdate;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.ImportRequest;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.PageFilter;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.Save;
import com.adpulse.main.adaccountasset.AdAccountAssetRequests.SpreadsheetUpdate;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.Account;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.AccountAttribute;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.DailyLimitChangePage;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.FacebookActivityPage;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportFailedFile;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportHistory;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportResult;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.LifecycleDetail;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.Page;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.SpreadsheetSaveResult;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.MediaType;
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

/** 资产管理页使用的广告账户清单与资产信息接口。 */
@RestController
@RequestMapping("/asset-management/ad-accounts")
public class AdAccountAssetController {
    private final AdAccountAssetService service;
    private final AdAccountImportService importService;
    private final FacebookAdActivityService facebookActivityService;
    private final AdAccountDailyLimitChangeService dailyLimitChangeService;

    public AdAccountAssetController(
            AdAccountAssetService service,
            AdAccountImportService importService,
            FacebookAdActivityService facebookActivityService,
            AdAccountDailyLimitChangeService dailyLimitChangeService) {
        this.service = service;
        this.importService = importService;
        this.facebookActivityService = facebookActivityService;
        this.dailyLimitChangeService = dailyLimitChangeService;
    }

    @GetMapping
    public ApiResponse<Page> list(
            @RequestParam(required = false) String keyword,
            @RequestParam(name = "accountName", required = false) List<String> accountNames,
            @RequestParam(name = "accountId", required = false) List<String> accountIds,
            @RequestParam(name = "accountStatus", required = false) List<Integer> accountStatuses,
            @RequestParam(name = "accountType", required = false) List<String> accountTypes,
            @RequestParam(name = "accountAttribute", required = false)
                    List<String> accountAttributes,
            @RequestParam(name = "channelName", required = false) List<String> channelNames,
            @RequestParam(name = "managedBm", required = false) List<String> managedBms,
            @RequestParam(name = "managedBmId", required = false) List<String> managedBmIds,
            @RequestParam(name = "backupManagedBm", required = false) List<String> backupManagedBms,
            @RequestParam(name = "backupManagedBmId", required = false)
                    List<String> backupManagedBmIds,
            @RequestParam(name = "timezone", required = false) List<String> timezones,
            @RequestParam(name = "cardStation", required = false) List<String> cardStations,
            @RequestParam(name = "cardNumber", required = false) List<String> cardNumbers,
            @RequestParam(name = "inventoryStatus", required = false)
                    List<String> inventoryStatuses,
            @RequestParam(name = "usageUsers", required = false) List<String> usageUsers,
            @RequestParam(name = "usageDepartment", required = false) List<String> usageDepartments,
            @RequestParam(name = "inventoryAssigneeName", required = false)
                    List<String> inventoryAssigneeNames,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        PageFilter filter =
                new PageFilter(
                        accountNames,
                        accountIds,
                        accountStatuses,
                        accountTypes,
                        accountAttributes,
                        channelNames,
                        managedBms,
                        managedBmIds,
                        backupManagedBms,
                        backupManagedBmIds,
                        timezones,
                        cardStations,
                        cardNumbers,
                        inventoryStatuses,
                        usageUsers,
                        usageDepartments,
                        inventoryAssigneeNames);
        return ApiResponse.success(service.list(keyword, filter, page, pageSize));
    }

    /** 按列表相同筛选口径一次返回全部广告账户，供导出和跨页批量处理使用。 */
    @PostMapping("/search-all")
    public ApiResponse<List<Account>> searchAll(@Valid @RequestBody AccountSearch request) {
        return ApiResponse.success(service.listAll(request.keyword(), request.filter()));
    }

    /** 查询广告账户自身的入库、分配与释放生命周期；申请审批事件由 system 服务提供。 */
    @GetMapping("/{accountId}/lifecycle")
    public ApiResponse<LifecycleDetail> lifecycle(@PathVariable String accountId) {
        return ApiResponse.success(service.lifecycle(accountId));
    }

    /** 分页查询广告账户自入库以来的 Facebook 平台操作记录。 */
    @GetMapping("/{accountId}/facebook-activities")
    public ApiResponse<FacebookActivityPage> facebookActivities(
            @PathVariable String accountId,
            @RequestParam(required = false) String after,
            @RequestParam(required = false) Long until,
            @RequestParam(defaultValue = "50") int pageSize) {
        return ApiResponse.success(facebookActivityService.list(accountId, after, until, pageSize));
    }

    /** 分页查询广告账户的日限额变化记录。 */
    @GetMapping("/{accountId}/daily-limit-changes")
    public ApiResponse<DailyLimitChangePage> dailyLimitChanges(
            @PathVariable String accountId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(dailyLimitChangeService.list(accountId, page, pageSize));
    }

    /** 批量返回广告账户资产台账，保证跨页面使用同一套字段取值优先级。 */
    @PostMapping("/batch")
    public ApiResponse<List<Account>> batch(@Valid @RequestBody AccountBatchQuery request) {
        return ApiResponse.success(service.listByAccountIds(request.accountIds()));
    }

    /** 按显式字段白名单批量覆盖广告账户的可编辑资料。 */
    @PatchMapping("/batch")
    public ApiResponse<List<Account>> batchUpdate(@Valid @RequestBody BatchUpdate request) {
        return ApiResponse.success(service.batchUpdate(request));
    }

    /** 电子表格中的全部行在同一事务内新增或更新。 */
    @PostMapping("/spreadsheet")
    public ApiResponse<SpreadsheetSaveResult> spreadsheetUpdate(
            @Valid @RequestBody SpreadsheetUpdate request) {
        return ApiResponse.success(service.spreadsheetUpdate(request));
    }

    /** 渠道管理按渠道名称精准查询广告账户资产。 */
    @GetMapping("/by-channel")
    public ApiResponse<List<Account>> byChannel(@RequestParam String channelName) {
        return ApiResponse.success(service.listByChannelName(channelName));
    }

    /** 返回当前登录用户正在使用的广告账户。 */
    @GetMapping("/mine")
    public ApiResponse<List<Account>> mine() {
        return ApiResponse.success(service.listMine());
    }

    @PutMapping("/{accountId}")
    public ApiResponse<Account> update(
            @PathVariable String accountId, @Valid @RequestBody Save request) {
        return ApiResponse.success(service.update(accountId, request));
    }

    /** 解除人工锁定，允许飞书任务继续维护账户业务资料。 */
    @PostMapping("/{accountId}/resume-sync")
    public ApiResponse<Account> resumeSync(@PathVariable String accountId) {
        return ApiResponse.success(service.resumeAutomaticSync(accountId));
    }

    /** 为一个或多个广告账户幂等分配使用人。 */
    @PostMapping("/assignments")
    public ApiResponse<List<Account>> assign(@Valid @RequestBody AssignmentSave request) {
        return ApiResponse.success(service.assign(request));
    }

    /** 整体替换指定广告账户的当前使用人集合。 */
    @PutMapping("/{accountId}/assignments")
    public ApiResponse<Account> replaceAssignments(
            @PathVariable String accountId, @Valid @RequestBody AssignmentReplace request) {
        return ApiResponse.success(service.replaceAssignments(accountId, request));
    }

    @PostMapping("/import")
    public ApiResponse<ImportResult> importAccounts(@Valid @RequestBody ImportRequest request) {
        return ApiResponse.success(service.importAccounts(request.items()));
    }

    /** 上传广告账户文件，由 main 服务统一解析表头并执行逐行业务校验。 */
    @PostMapping(value = "/import-file", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<ImportResult> importAccountFile(@RequestPart("file") MultipartFile file)
            throws java.io.IOException {
        if (file.isEmpty()) throw new AdAccountAssetService.AdAccountAssetException("请选择导入文件");
        if (file.getSize() > 5L * 1024 * 1024) {
            throw new AdAccountAssetService.AdAccountAssetException("导入文件不能超过 5MB");
        }
        return ApiResponse.success(
                importService.importFile(file.getBytes(), file.getOriginalFilename()));
    }

    /** 查询当前登录用户自己的广告账户导入记录。 */
    @GetMapping("/import-records")
    public ApiResponse<List<ImportHistory>> importHistory() {
        return ApiResponse.success(importService.history());
    }

    /** 下载当前登录用户自己的广告账户导入失败工作簿。 */
    @GetMapping("/import-records/{id}/failed-file")
    public ApiResponse<ImportFailedFile> importFailedFile(@PathVariable Long id) {
        return ApiResponse.success(importService.failedFile(id));
    }

    /** 查询账户属性配置。 */
    @GetMapping("/attributes")
    public ApiResponse<List<AccountAttribute>> attributes() {
        return ApiResponse.success(service.listAccountAttributes());
    }

    /** 新增账户属性配置。 */
    @PostMapping("/attributes")
    public ApiResponse<AccountAttribute> createAttribute(
            @Valid @RequestBody AccountAttributeSave request) {
        return ApiResponse.success(service.createAccountAttribute(request));
    }

    /** 修改账户属性配置。 */
    @PutMapping("/attributes/{id}")
    public ApiResponse<AccountAttribute> updateAttribute(
            @PathVariable Long id, @Valid @RequestBody AccountAttributeSave request) {
        return ApiResponse.success(service.updateAccountAttribute(id, request));
    }

    /** 删除账户属性配置；已使用的账户属性保留为历史值。 */
    @DeleteMapping("/attributes/{id}")
    public ApiResponse<Void> deleteAttribute(@PathVariable Long id) {
        service.deleteAccountAttribute(id);
        return ApiResponse.success();
    }
}
