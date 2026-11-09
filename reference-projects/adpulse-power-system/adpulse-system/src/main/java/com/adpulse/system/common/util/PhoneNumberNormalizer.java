package com.adpulse.system.common.util;

import java.util.regex.Pattern;
import org.springframework.util.StringUtils;

/** 手机号标准化工具，统一将中国大陆本地号码转换为带国家码的 E.164 格式。 */
public final class PhoneNumberNormalizer {

    private static final Pattern CHINA_LOCAL_PHONE = Pattern.compile("^1[3-9]\\d{9}$");

    private PhoneNumberNormalizer() {}

    /** 将 11 位中国大陆手机号转换为 +86 格式；其他国际号码仅去除首尾空白。 */
    public static String normalize(String phone) {
        if (!StringUtils.hasText(phone)) {
            return null;
        }
        String trimmed = phone.trim();
        return CHINA_LOCAL_PHONE.matcher(trimmed).matches() ? "+86" + trimmed : trimmed;
    }
}
