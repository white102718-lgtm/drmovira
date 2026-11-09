package com.ruoyi.web.controller.orbit;

import com.ruoyi.system.orbit.scope.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;

/** 原合同范围入口；CSRF签发是若依Bearer会话适配扩展，不改变若依原登录。 */
@RestController
@RequestMapping("/api/v1/scope-snapshots")
public class OrbitScopeController {
    private final ScopeHttpService service;

    public OrbitScopeController(ScopeHttpService service) {
        this.service = service;
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(@RequestParam MultiValueMap<String, String> query) {
        if (!query.isEmpty()) throw invalid(400, "UNKNOWN_FIELD", "签发接口不接受查询参数");
        return service.csrf();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ScopeHttpService.View create(
            @RequestBody String body, HttpServletRequest request, HttpServletResponse response) {
        if (!request.getParameterMap().isEmpty())
            throw invalid(400, "UNKNOWN_FIELD", "创建接口不接受查询参数");
        // 每次HTTP请求独立生成，绝不信任客户端同名头，也不作为业务幂等键。
        String requestId = UUID.randomUUID().toString();
        var result =
                service.create(
                        header(request, "Idempotency-Key", true),
                        header(request, "X-CSRF-Token", true),
                        header(request, "X-Target-Tenant", false),
                        body,
                        requestId);
        // 成功提交后才写响应头；失败交由统一异常处理器生成同一头/错误体ID，避免重复头。
        response.setHeader("X-Request-ID", requestId);
        return result;
    }

    @GetMapping("/{id}/members")
    public ScopeMemberPager.Page members(
            @PathVariable String id, @RequestParam MultiValueMap<String, String> query) {
        Set<String> all =
                Set.of(
                        "q",
                        "cursor",
                        "page_size",
                        "status",
                        "date_from",
                        "date_to",
                        "operator_user_id",
                        "channel_id",
                        "metric_profile_id",
                        "entity_type");
        for (var field : query.entrySet()) {
            if (!all.contains(field.getKey())) throw invalid(400, "UNKNOWN_FIELD", "查询包含未知参数");
            if (field.getValue().size() != 1) throw invalid(400, "INVALID_REQUEST", "查询参数不能重复");
            if (!Set.of("q", "cursor", "page_size").contains(field.getKey()))
                throw invalid(422, "UNSUPPORTED_FILTER", "冻结成员不支持该过滤组合");
        }
        String size = query.getFirst("page_size");
        int pageSize = 50;
        if (size != null) {
            if (!Set.of("20", "50", "100", "200").contains(size))
                throw invalid(422, "BUSINESS_VALIDATION_FAILED", "页大小仅支持20/50/100/200");
            pageSize = Integer.parseInt(size);
        }
        return service.members(id, query.getFirst("q"), pageSize, query.getFirst("cursor"));
    }

    private String header(HttpServletRequest request, String name, boolean required) {
        var values = Collections.list(request.getHeaders(name));
        if (values.size() > 1 || (required && values.isEmpty()))
            throw invalid(400, "INVALID_REQUEST", "必需请求头缺失或重复");
        return values.isEmpty() ? null : values.getFirst();
    }

    private AccountScopeService.Failure invalid(int status, String code, String message) {
        return new AccountScopeService.Failure(status, code, message);
    }
}
