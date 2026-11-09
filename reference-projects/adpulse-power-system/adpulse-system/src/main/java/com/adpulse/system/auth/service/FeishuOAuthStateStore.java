package com.adpulse.system.auth.service;

import com.adpulse.system.config.FeishuOAuthProperties;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Redis 飞书 OAuth 一次性 state 存储。 */
@Component
public class FeishuOAuthStateStore {

    private static final String STATE_PREFIX = "adpulse:feishu:oauth:state:";

    private final StringRedisTemplate redisTemplate;
    private final FeishuOAuthProperties properties;
    private final SecureRandom secureRandom = new SecureRandom();

    public FeishuOAuthStateStore(
            StringRedisTemplate redisTemplate, FeishuOAuthProperties properties) {
        this.redisTemplate = redisTemplate;
        this.properties = properties;
    }

    /** 创建短期随机 state，防止登录回调被伪造。 */
    public String create() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        String state = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        redisTemplate.opsForValue().set(key(state), "1", properties.stateTtl());
        return state;
    }

    /** 原子消费 state，确保同一次扫码回调只能登录一次。 */
    public boolean consume(String state) {
        return redisTemplate.opsForValue().getAndDelete(key(state)) != null;
    }

    /** 返回 state 有效秒数。 */
    public long ttlSeconds() {
        return properties.stateTtl().toSeconds();
    }

    private String key(String state) {
        return STATE_PREFIX + state;
    }
}
