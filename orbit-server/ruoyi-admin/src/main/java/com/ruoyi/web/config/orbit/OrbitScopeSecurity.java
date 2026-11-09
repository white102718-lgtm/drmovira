package com.ruoyi.web.config.orbit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ruoyi.framework.security.filter.JwtAuthenticationTokenFilter;
import com.ruoyi.web.controller.orbit.OrbitScopeExceptionHandler;
import org.springframework.context.annotation.*;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.*;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.CorsFilter;

/** 仅新增范围路由使用真实HTTP401；CSRF由事务服务校验会话绑定令牌，原若依行为保留。 */
@Configuration
public class OrbitScopeSecurity {
    @Bean
    @Order(0)
    public SecurityFilterChain orbitScopeChain(
            HttpSecurity http, JwtAuthenticationTokenFilter jwt, CorsFilter cors, ObjectMapper json)
            throws Exception {
        return http.securityMatcher(
                        "/api/v1/scope-snapshots",
                        "/api/v1/scope-snapshots/**",
                        "/api/v1/audit-events")
                .csrf(c -> c.disable())
                .formLogin(c -> c.disable())
                .httpBasic(c -> c.disable())
                .requestCache(c -> c.disable())
                .sessionManagement(c -> c.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(c -> c.anyRequest().authenticated())
                .headers(
                        c ->
                                c.addHeaderWriter(
                                        (request, response) -> {
                                            response.setHeader("Cache-Control", "no-store");
                                            response.setHeader("Pragma", "no-cache");
                                        }))
                .exceptionHandling(
                        c ->
                                c.authenticationEntryPoint(
                                        (request, response, error) -> {
                                            var rejected =
                                                    OrbitScopeExceptionHandler.error(
                                                            401, "SESSION_REQUIRED", "请重新登录");
                                            response.setStatus(401);
                                            response.setContentType(
                                                    "application/json;charset=UTF-8");
                                            response.setHeader(
                                                    "X-Request-ID",
                                                    rejected.getHeaders().getFirst("X-Request-ID"));
                                            json.writeValue(
                                                    response.getWriter(), rejected.getBody());
                                        }))
                .addFilterBefore(jwt, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(cors, JwtAuthenticationTokenFilter.class)
                .build();
    }
}
