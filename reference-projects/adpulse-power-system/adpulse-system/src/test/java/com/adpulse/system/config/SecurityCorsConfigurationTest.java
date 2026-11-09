package com.adpulse.system.config;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;

/** 全局开放跨域策略配置测试。 */
class SecurityCorsConfigurationTest {

    @Test
    void shouldAllowAllOriginsMethodsAndHeadersWithoutCookieCredentials() {
        CorsConfigurationSource source = new SecurityConfig().corsConfigurationSource();
        HttpServletRequest request = new MockHttpServletRequest("OPTIONS", "/api/auth/login");

        CorsConfiguration configuration = source.getCorsConfiguration(request);

        assertThat(configuration).isNotNull();
        assertThat(configuration.getAllowedOriginPatterns())
                .isEqualTo(List.of(CorsConfiguration.ALL));
        assertThat(configuration.getAllowedMethods()).isEqualTo(List.of(CorsConfiguration.ALL));
        assertThat(configuration.getAllowedHeaders()).isEqualTo(List.of(CorsConfiguration.ALL));
        assertThat(configuration.getAllowCredentials()).isFalse();
        assertThat(configuration.getExposedHeaders())
                .contains("Authorization", "Content-Disposition", "Content-Length");
        assertThat(configuration.getMaxAge()).isEqualTo(3600L);
    }
}
