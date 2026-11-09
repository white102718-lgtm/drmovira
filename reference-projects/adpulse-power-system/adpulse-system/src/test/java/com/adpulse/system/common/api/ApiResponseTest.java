package com.adpulse.system.common.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** 统一响应协议测试。 */
class ApiResponseTest {

    @Test
    void shouldUseHttpStyleSuccessCode() {
        ApiResponse<String> response = ApiResponse.success("ok");

        assertThat(response.code()).isEqualTo(200);
        assertThat(response.message()).isEqualTo("success");
        assertThat(response.data()).isEqualTo("ok");
    }

    @Test
    void shouldRejectNonThreeDigitCode() {
        assertThatThrownBy(() -> ApiResponse.failure(50000, "invalid"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("三位整数");
    }
}
