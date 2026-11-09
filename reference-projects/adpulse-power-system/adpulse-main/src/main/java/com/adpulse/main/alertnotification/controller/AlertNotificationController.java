package com.adpulse.main.alertnotification.controller;

import com.adpulse.main.alertnotification.dto.AlertRequests.ConfigSave;
import com.adpulse.main.alertnotification.dto.AlertRequests.EventRecordQuery;
import com.adpulse.main.alertnotification.dto.AlertRequests.LimitChangeRecordQuery;
import com.adpulse.main.alertnotification.dto.AlertRequests.TestDelivery;
import com.adpulse.main.alertnotification.dto.AlertViews.BanRecord;
import com.adpulse.main.alertnotification.dto.AlertViews.LimitChangeRecord;
import com.adpulse.main.alertnotification.dto.AlertViews.Page;
import com.adpulse.main.alertnotification.dto.AlertViews.Settings;
import com.adpulse.main.alertnotification.dto.AlertViews.TestDeliveryResult;
import com.adpulse.main.alertnotification.service.AlertEventRecordService;
import com.adpulse.main.alertnotification.service.AlertNotificationService;
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.security.CurrentUser;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 预警配置和提醒记录接口。 */
@RestController
@RequestMapping("/alert-notifications")
public class AlertNotificationController {
    private final AlertNotificationService service;
    private final AlertEventRecordService eventRecordService;

    public AlertNotificationController(
            AlertNotificationService service, AlertEventRecordService eventRecordService) {
        this.service = service;
        this.eventRecordService = eventRecordService;
    }

    @GetMapping("/settings")
    public ApiResponse<Settings> settings() {
        return ApiResponse.success(service.settings());
    }

    @PutMapping("/settings")
    public ApiResponse<Settings> save(
            @Valid @RequestBody ConfigSave request,
            @AuthenticationPrincipal CurrentUser currentUser) {
        return ApiResponse.success(service.save(request, currentUser.userId()));
    }

    @PostMapping("/test-delivery")
    public ApiResponse<TestDeliveryResult> testDelivery(@Valid @RequestBody TestDelivery request) {
        return ApiResponse.success(service.testDelivery(request));
    }

    /** 按平台事件发生时间倒序分页查询封户记录。 */
    @GetMapping("/ban-records")
    public ApiResponse<Page<BanRecord>> banRecords(EventRecordQuery query) {
        return ApiResponse.success(eventRecordService.listBanRecords(query));
    }

    /** 按平台事件发生时间倒序分页查询账户日限额变化记录。 */
    @GetMapping("/limit-change-records")
    public ApiResponse<Page<LimitChangeRecord>> limitChangeRecords(LimitChangeRecordQuery query) {
        return ApiResponse.success(eventRecordService.listLimitChangeRecords(query));
    }
}
