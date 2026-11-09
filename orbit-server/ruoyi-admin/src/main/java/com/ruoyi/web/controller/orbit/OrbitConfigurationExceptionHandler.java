package com.ruoyi.web.controller.orbit;

import com.ruoyi.system.orbit.config.ConfigurationException;
import java.util.Map;
import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.ServletRequestBindingException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 配置接口独立安全错误边界，禁止默认异常日志打印请求值或SQL参数。 */
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(assignableTypes = OrbitConfigurationController.class)
public class OrbitConfigurationExceptionHandler
        implements org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice<
                Object> {
    @Override
    public boolean supports(
            org.springframework.core.MethodParameter parameter,
            Class<? extends org.springframework.http.converter.HttpMessageConverter<?>> converter) {
        return true;
    }

    /** 浏览器及中间代理不能缓存配置详情或错误响应。 */
    @Override
    public Object beforeBodyWrite(
            Object body,
            org.springframework.core.MethodParameter parameter,
            org.springframework.http.MediaType mediaType,
            Class<? extends org.springframework.http.converter.HttpMessageConverter<?>> converter,
            org.springframework.http.server.ServerHttpRequest request,
            org.springframework.http.server.ServerHttpResponse response) {
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().setPragma("no-cache");
        return body;
    }

    @ExceptionHandler(ConfigurationException.class)
    public ResponseEntity<Map<String, Object>> business(ConfigurationException exception) {
        return error(exception.status(), exception.code(), exception.getMessage());
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<Map<String, Object>> forbidden() {
        return error(403, "FORBIDDEN", "没有系统配置维护权限");
    }

    @ExceptionHandler({
        HttpMessageNotReadableException.class,
        ServletRequestBindingException.class,
        org.springframework.web.method.annotation.MethodArgumentTypeMismatchException.class
    })
    public ResponseEntity<Map<String, Object>> invalid() {
        return error(400, "INVALID_REQUEST", "请求结构或必需请求头不符合要求");
    }

    @ExceptionHandler(DuplicateKeyException.class)
    public ResponseEntity<Map<String, Object>> duplicate() {
        return error(409, "DUPLICATE_CONFIGURATION", "同类型配置名称已存在，请修改后重试");
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> unexpected() {
        // 不返回原异常message，也不记录可能带有平台响应/凭据的堆栈。
        return error(500, "CONFIGURATION_UNAVAILABLE", "系统配置操作失败，请检查服务端密钥配置与数据库初始化状态");
    }

    private static ResponseEntity<Map<String, Object>> error(
            int status, String code, String message) {
        String requestId = UUID.randomUUID().toString();
        return ResponseEntity.status(status)
                .header("X-Request-ID", requestId)
                .body(Map.of("code", code, "message", message, "request_id", requestId));
    }
}
