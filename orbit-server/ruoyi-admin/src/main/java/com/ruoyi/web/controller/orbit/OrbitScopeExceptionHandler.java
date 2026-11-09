package com.ruoyi.web.controller.orbit;

import com.ruoyi.system.orbit.rules.RuleDraftStore;
import com.ruoyi.system.orbit.scope.AccountScopeService;
import java.util.*;
import org.springframework.core.*;
import org.springframework.core.annotation.Order;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

/** 固定合同错误与no-store；不记录URL、请求正文、游标、JWT或原数据库异常。 */
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(assignableTypes = {OrbitScopeController.class, OrbitAuditController.class})
public class OrbitScopeExceptionHandler implements ResponseBodyAdvice<Object> {
    @Override
    public boolean supports(MethodParameter parameter, Class converter) {
        return true;
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter parameter,
            MediaType type,
            Class converter,
            org.springframework.http.server.ServerHttpRequest request,
            org.springframework.http.server.ServerHttpResponse response) {
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().setPragma("no-cache");
        if (!response.getHeaders().containsKey("X-Request-ID"))
            response.getHeaders().set("X-Request-ID", UUID.randomUUID().toString());
        return body;
    }

    @ExceptionHandler(AccountScopeService.Failure.class)
    public ResponseEntity<Map<String, Object>> failure(AccountScopeService.Failure error) {
        return error(error.status(), error.code(), error.getMessage());
    }

    @ExceptionHandler(RuleDraftStore.Failure.class)
    public ResponseEntity<Map<String, Object>> ownership(RuleDraftStore.Failure error) {
        return error(
                error.status(),
                error.status() == 404 ? "NOT_FOUND" : "PERMISSION_DENIED",
                "对象不存在或当前授权不足");
    }

    @ExceptionHandler({
        org.springframework.http.converter.HttpMessageNotReadableException.class,
        org.springframework.web.bind.ServletRequestBindingException.class
    })
    public ResponseEntity<Map<String, Object>> invalid() {
        return error(400, "INVALID_REQUEST", "请求结构或必要请求头无效");
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> unexpected() {
        return error(503, "DEPENDENCY_UNAVAILABLE", "业务查询服务暂不可用");
    }

    public static ResponseEntity<Map<String, Object>> error(
            int status, String code, String message) {
        String id = UUID.randomUUID().toString();
        return ResponseEntity.status(status)
                .header("X-Request-ID", id)
                .header("Cache-Control", "no-store")
                .body(
                        Map.of(
                                "code",
                                code,
                                "message",
                                message,
                                "field_errors",
                                List.of(),
                                "retryable",
                                status == 429 || status == 503,
                                "request_id",
                                id));
    }
}
