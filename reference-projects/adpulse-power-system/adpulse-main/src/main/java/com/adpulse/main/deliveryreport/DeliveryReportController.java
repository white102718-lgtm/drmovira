package com.adpulse.main.deliveryreport;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.*;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

/** 本人投放日报接口，用户身份始终由已验证的会话解析。 */
@RestController
@RequestMapping("/delivery-reports")
public class DeliveryReportController {
    private final DeliveryReportService service;

    public DeliveryReportController(DeliveryReportService service) {
        this.service = service;
    }

    /** 获取可选择的项目和代理线。 */
    @GetMapping("/options")
    public ApiResponse<List<LineOption>> options() {
        return ApiResponse.success(service.options());
    }

    /** 查询当天平台数据及本人已保存记录。 */
    @GetMapping
    public ApiResponse<Result> query(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date) {
        return ApiResponse.success(service.query(date));
    }

    /** 按时间段返回本人绩效统计的数据源。 */
    @GetMapping("/performance")
    public ApiResponse<PerformanceResult> performance(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(required = false) Long reporterId) {
        return ApiResponse.success(service.performance(startDate, endDate, reporterId));
    }

    /** 返回当前会话有权查看的人员。 */
    @GetMapping("/reporters")
    public ApiResponse<List<Reporter>> reporters() {
        return ApiResponse.success(service.reporters());
    }

    /** 只读列表；不复用填写入口，避免他人平台未填数据被展示。 */
    @GetMapping("/read")
    public ApiResponse<List<Result>> read(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate date,
            @RequestParam(required = false) Long reporterId) {
        return ApiResponse.success(service.read(date, reporterId));
    }

    /** 保存日报和截图关联，不发起审批。 */
    @GetMapping("/page")
    public ApiResponse<ReadPage> page(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(required = false) Long reporterId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize,
            @RequestParam(required = false) String reporter,
            @RequestParam(required = false) String project,
            @RequestParam(required = false) String line) {
        return ApiResponse.success(
                service.page(
                        startDate, endDate, reporterId, page, pageSize, reporter, project, line));
    }

    /** 全量筛选范围统计，不依赖列表分页。 */
    @GetMapping("/stats")
    public ApiResponse<ReadStats> stats(
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate startDate,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate endDate,
            @RequestParam(required = false) Long reporterId,
            @RequestParam(required = false) String reporter,
            @RequestParam(required = false) String project,
            @RequestParam(required = false) String line) {
        return ApiResponse.success(
                service.stats(startDate, endDate, reporterId, reporter, project, line));
    }

    /** 保存日报和截图关联，不发起审批。 */
    @PutMapping
    public ApiResponse<Result> save(@Valid @RequestBody SaveRequest request) {
        return ApiResponse.success(service.save(request));
    }
}
