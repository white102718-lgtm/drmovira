package com.adpulse.main.config;

import com.adpulse.main.cloak.config.GlobalPwaProperties;
import com.adpulse.main.google.config.GoogleIntegrationProperties;
import com.adpulse.main.google.config.GoogleServiceAccountProperties;
import com.adpulse.main.project.wallet.mpower.MpowerWalletProperties;
import com.adpulse.system.auth.security.JwtSessionFilter;
import com.adpulse.system.common.api.ApiCode;
import com.adpulse.system.config.SecurityProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

/** 主业务服务的无状态Web安全配置。 */
@Configuration
@EnableMethodSecurity
@EnableConfigurationProperties({
    SecurityProperties.class,
    GoogleIntegrationProperties.class,
    GoogleServiceAccountProperties.class,
    GlobalPwaProperties.class,
    MpowerWalletProperties.class
})
public class MainSecurityConfig {

    /** 所有业务接口均要求通过共享JWT与Redis会话认证。 */
    @Bean
    SecurityFilterChain mainSecurityFilterChain(
            HttpSecurity http,
            JwtSessionFilter jwtSessionFilter,
            ObjectMapper objectMapper,
            @Qualifier("mainCorsConfigurationSource") CorsConfigurationSource corsConfigurationSource)
            throws Exception {
        http.csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsConfigurationSource))
                .sessionManagement(
                        session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(
                        requests ->
                                requests.requestMatchers(HttpMethod.OPTIONS, "/**")
                                        .permitAll()
                                        .requestMatchers("/error")
                                        .permitAll()
                                        .requestMatchers(
                                                HttpMethod.GET, "/data-integration/oauth/callback")
                                        .permitAll()
                                        .anyRequest()
                                        .authenticated())
                .exceptionHandling(
                        handling ->
                                handling.authenticationEntryPoint(
                                                (request, response, exception) ->
                                                        writeError(
                                                                response,
                                                                objectMapper,
                                                                ApiCode.SESSION_INVALID,
                                                                "登录状态无效或已过期"))
                                        .accessDeniedHandler(
                                                (request, response, exception) ->
                                                        writeError(
                                                                response,
                                                                objectMapper,
                                                                ApiCode.ACCESS_DENIED,
                                                                "没有访问权限")))
                .addFilterBefore(jwtSessionFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    /** 与系统服务保持一致的联调期跨域策略。 */
    @Bean
    CorsConfigurationSource mainCorsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOriginPatterns(List.of(CorsConfiguration.ALL));
        configuration.setAllowedMethods(List.of(CorsConfiguration.ALL));
        configuration.setAllowedHeaders(List.of(CorsConfiguration.ALL));
        configuration.setExposedHeaders(
                List.of("Authorization", "Content-Disposition", "Content-Length"));
        configuration.setAllowCredentials(false);
        configuration.setMaxAge(3600L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    private void writeError(
            HttpServletResponse response, ObjectMapper objectMapper, int code, String message)
            throws java.io.IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(
                response.getOutputStream(), Map.of("code", code, "message", message, "data", ""));
    }
}
