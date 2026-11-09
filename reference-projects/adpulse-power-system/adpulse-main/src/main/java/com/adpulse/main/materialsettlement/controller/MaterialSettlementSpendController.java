package com.adpulse.main.materialsettlement.controller;

import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendRequests;
import com.adpulse.main.materialsettlement.dto.MaterialSettlementSpendViews;
import com.adpulse.main.materialsettlement.service.MaterialSettlementSpendService;
import com.adpulse.system.common.api.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 素材师月报结算花费接口。 */
@RestController
@RequestMapping("/material-settlement")
public class MaterialSettlementSpendController {
    private final MaterialSettlementSpendService service;

    public MaterialSettlementSpendController(MaterialSettlementSpendService service) {
        this.service = service;
    }

    /** 按结算自然月批量精确查询月报中所选任务线的花费。 */
    @PostMapping("/task-line-spends")
    public ApiResponse<MaterialSettlementSpendViews.TaskLineSpendResult> queryTaskLineSpends(
            @Valid @RequestBody MaterialSettlementSpendRequests.TaskLineSpendQuery request) {
        return ApiResponse.success(service.queryTaskLineSpends(request));
    }
}
