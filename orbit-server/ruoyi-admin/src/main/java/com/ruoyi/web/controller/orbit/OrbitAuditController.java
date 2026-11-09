package com.ruoyi.web.controller.orbit;

import com.ruoyi.system.orbit.scope.*;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;

/** 审计只读合同入口；身份和全部可见租户均由当前服务端会话取得。 */
@RestController
@RequestMapping("/api/v1/audit-events")
public class OrbitAuditController {
    private final AuditEventsService service;

    public OrbitAuditController(AuditEventsService service) {
        this.service = service;
    }

    @GetMapping
    public AuditEventsService.Page list(
            @RequestParam MultiValueMap<String, String> query, HttpServletRequest request) {
        if (request.getHeader("X-Target-Tenant") != null)
            throw new AccountScopeService.Failure(403, "PERMISSION_DENIED", "审计查询不接受写入目标租户头");
        return service.pageTrusted(query);
    }
}
