package com.adpulse.system.config;

import com.adpulse.system.auth.security.JwtSessionFilter;
import com.adpulse.system.common.api.ApiCode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

/** Spring Security 过滤器链与密码算法配置。 */
@Configuration
@EnableMethodSecurity
@EnableConfigurationProperties({
    SecurityProperties.class,
    MfaProperties.class,
    FeishuOAuthProperties.class
})
public class SecurityConfig {

    /** 配置无容器会话的 API 安全过滤器链。 */
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JwtSessionFilter jwtSessionFilter,
            ObjectMapper objectMapper,
            Environment environment,
            @Qualifier("corsConfigurationSource") CorsConfigurationSource corsConfigurationSource)
            throws Exception {
        http.csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsConfigurationSource))
                .sessionManagement(
                        session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(
                        requests -> {
                            // CORS 预检请求：任何路径的 OPTIONS 都直接放行，避免被鉴权拦截
                            requests.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll();
                            requests.requestMatchers(
                                            "/auth/login",
                                            "/auth/mfa/**",
                                            "/auth/feishu/**",
                                            "/error")
                                    .permitAll();
                            if (environment.matchesProfiles("test")) {
                                requests.requestMatchers(
                                                "/doc.html",
                                                "/webjars/**",
                                                "/v3/api-docs/**",
                                                "/swagger-ui/**",
                                                "/swagger-ui.html")
                                        .permitAll();
                            }
                            requests.anyRequest().authenticated();
                        })
                .exceptionHandling(
                        handling ->
                                handling.authenticationEntryPoint(
                                                (request, response, exception) -> {
                                                    response.setStatus(HttpServletResponse.SC_OK);
                                                    response.setContentType(
                                                            MediaType.APPLICATION_JSON_VALUE);
                                                    objectMapper.writeValue(
                                                            response.getOutputStream(),
                                                            java.util.Map.of(
                                                                    "code", ApiCode.SESSION_INVALID,
                                                                    "message", "登录状态无效或已过期",
                                                                    "data", ""));
                                                })
                                        .accessDeniedHandler(
                                                (request, response, exception) -> {
                                                    response.setStatus(HttpServletResponse.SC_OK);
                                                    response.setContentType(
                                                            MediaType.APPLICATION_JSON_VALUE);
                                                    objectMapper.writeValue(
                                                            response.getOutputStream(),
                                                            java.util.Map.of(
                                                                    "code", ApiCode.ACCESS_DENIED,
                                                                    "message", "没有访问权限",
                                                                    "data", ""));
                                                }))
                .addFilterBefore(jwtSessionFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    /** 允许任意来源、方法和请求头跨域访问，认证与授权规则保持不变。 */
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        // 使用 allowedOriginPatterns=* 允许任意来源（含端口），避免浏览器预检失败
        configuration.setAllowedOriginPatterns(List.of(CorsConfiguration.ALL));
        configuration.setAllowedMethods(List.of(CorsConfiguration.ALL));
        configuration.setAllowedHeaders(List.of(CorsConfiguration.ALL));
        // 暴露前端读取文件下载名 / JWT 头所需字段
        configuration.setExposedHeaders(
                List.of("Authorization", "Content-Disposition", "Content-Length"));
        // allowCredentials=false，避免浏览器在非 same-site 时拦截响应
        configuration.setAllowCredentials(false);
        // 预检缓存 1 小时，减少重复 OPTIONS 请求
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    /** 使用 BCrypt 保存密码，编码强度采用框架安全默认值。 */
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
