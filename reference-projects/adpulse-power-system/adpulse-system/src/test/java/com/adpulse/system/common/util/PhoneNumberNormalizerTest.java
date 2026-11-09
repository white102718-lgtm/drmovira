package com.adpulse.system.common.util;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** 手机号标准化测试。 */
class PhoneNumberNormalizerTest {

    @Test
    void shouldNormalizeChinaPhoneAndKeepInternationalFormat() {
        assertThat(PhoneNumberNormalizer.normalize("13800000000")).isEqualTo("+8613800000000");
        assertThat(PhoneNumberNormalizer.normalize("+8613800000000")).isEqualTo("+8613800000000");
        assertThat(PhoneNumberNormalizer.normalize("+14155552671")).isEqualTo("+14155552671");
    }
}
