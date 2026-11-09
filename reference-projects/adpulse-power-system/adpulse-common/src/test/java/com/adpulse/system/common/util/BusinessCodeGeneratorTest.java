package com.adpulse.system.common.util;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNullPointerException;

import org.junit.jupiter.api.Test;

/** 公共业务编码的格式、时间戳及前缀边界测试。 */
class BusinessCodeGeneratorTest {

    @Test
    void shouldPreserveOriginalFormatAndCurrentTimestamp() {
        long before = System.currentTimeMillis();
        String code = BusinessCodeGenerator.generate("AUTO_");
        long after = System.currentTimeMillis();

        assertThat(code).matches("AUTO_[0-9A-Z]+_[0-9A-Z]{4}");
        assertThat(Long.parseLong(code.split("_")[1], 36)).isBetween(before, after);
    }

    @Test
    void shouldKeepCustomPrefixExactlyAsProvided() {
        assertThat(BusinessCodeGenerator.generate("order-")).matches("order-[0-9A-Z]+_[0-9A-Z]{4}");
        assertThat(BusinessCodeGenerator.generate("TASK_")).matches("TASK_[0-9A-Z]+_[0-9A-Z]{4}");
        assertThat(BusinessCodeGenerator.generate("")).matches("[0-9A-Z]+_[0-9A-Z]{4}");
    }

    @Test
    void shouldRejectNullPrefix() {
        assertThatNullPointerException()
                .isThrownBy(() -> BusinessCodeGenerator.generate(null))
                .withMessage("编码前缀不能为null");
    }
}
