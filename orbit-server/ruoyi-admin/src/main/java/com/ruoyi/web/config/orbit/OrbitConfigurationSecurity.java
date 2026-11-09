package com.ruoyi.web.config.orbit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.framework.security.filter.JwtAuthenticationTokenFilter;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.CorsFilter;

/** 仅覆盖新增系统配置接口，沿用若依JWT身份；原若依接口及布局不改变。 */
@Configuration
public class OrbitConfigurationSecurity {
    @Bean
    @Order(1)
    public SecurityFilterChain orbitConfigurationChain(
            HttpSecurity http, JwtAuthenticationTokenFilter jwt, CorsFilter cors, ObjectMapper json)
            throws Exception {
        return http.securityMatcher(
                        "/api/v1/system-configurations", "/api/v1/system-configurations/**")
                .csrf(csrf -> csrf.disable())
                .formLogin(login -> login.disable())
                .httpBasic(basic -> basic.disable())
                .requestCache(cache -> cache.disable())
                .sessionManagement(
                        session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(requests -> requests.anyRequest().authenticated())
                .headers(
                        headers ->
                                headers.addHeaderWriter(
                                        (request, response) -> {
                                            // 包括进入Controller之前的401/403，也不允许浏览器或代理缓存。
                                            response.setHeader("Cache-Control", "no-store");
                                            response.setHeader("Pragma", "no-cache");
                                        }))
                .exceptionHandling(
                        errors ->
                                errors.authenticationEntryPoint(
                                                (request, response, error) ->
                                                        reject(
                                                                response,
                                                                json,
                                                                401,
                                                                "UNAUTHENTICATED",
                                                                "登录已失效，请重新登录"))
                                        .accessDeniedHandler(
                                                (request, response, error) ->
                                                        reject(
                                                                response,
                                                                json,
                                                                403,
                                                                "FORBIDDEN",
                                                                "没有系统配置维护权限")))
                .addFilterBefore(jwt, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(cors, JwtAuthenticationTokenFilter.class)
                .build();
    }

    /** 固定脱敏错误，不回显URL、原异常、Authorization或请求体。 */
    private static void reject(
            HttpServletResponse response,
            ObjectMapper json,
            int status,
            String code,
            String message)
            throws IOException {
        String requestId = UUID.randomUUID().toString();
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("X-Request-ID", requestId);
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        json.writeValue(
                response.getWriter(),
                Map.of("code", code, "message", message, "request_id", requestId));
    }
}
