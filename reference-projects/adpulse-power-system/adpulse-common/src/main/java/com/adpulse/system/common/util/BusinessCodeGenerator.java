package com.adpulse.system.common.util;

import java.security.SecureRandom;
import java.util.Locale;
import java.util.Objects;

/** 各业务模块共享的时间戳与随机后缀编码生成工具。 */
public final class BusinessCodeGenerator {

    private static final int RADIX = 36;
    private static final int RANDOM_LENGTH = 4;
    private static final int RANDOM_BOUND = RADIX * RADIX * RADIX * RADIX;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private BusinessCodeGenerator() {}

    /**
     * 按“自定义前缀 + 大写36进制毫秒时间戳 + 下划线 + 4位大写36进制随机数”生成编码。
     *
     * <p>前缀原样保留，不自动补分隔符；例如传入 AUTO_ 可生成 AUTO_MTR8RT4H_1KB2。 随机后缀不足4位时左侧补零。编码低冲突但不保证唯一，持久化时仍需业务唯一约束。
     *
     * @param prefix 自定义前缀，可为空字符串，不可为 null
     * @return 包含前缀、时间戳和随机后缀的编码
     */
    public static String generate(String prefix) {
        Objects.requireNonNull(prefix, "编码前缀不能为null");
        String timestamp =
                Long.toString(System.currentTimeMillis(), RADIX).toUpperCase(Locale.ROOT);
        String random =
                Integer.toString(SECURE_RANDOM.nextInt(RANDOM_BOUND), RADIX)
                        .toUpperCase(Locale.ROOT);
        return prefix + timestamp + "_" + "0".repeat(RANDOM_LENGTH - random.length()) + random;
    }
}
