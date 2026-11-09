package com.adpulse.system.auth.service;

import com.adpulse.system.auth.model.MfaChallenge;
import com.adpulse.system.config.MfaProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Redis MFA一次性挑战存储。 */
@Component
public class MfaChallengeStore {

    private static final String CHALLENGE_PREFIX = "adpulse:mfa:challenge:";
    private static final String ATTEMPTS_PREFIX = "adpulse:mfa:attempts:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final MfaProperties properties;
    private final SecureRandom secureRandom = new SecureRandom();

    public MfaChallengeStore(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            MfaProperties properties) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    /** 创建短期随机挑战并返回不透明令牌。 */
    public String create(MfaChallenge challenge) {
        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(tokenBytes);
        try {
            redisTemplate
                    .opsForValue()
                    .set(
                            challengeKey(token),
                            objectMapper.writeValueAsString(challenge),
                            properties.challengeTtl());
            return token;
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("无法序列化MFA挑战", exception);
        }
    }

    /** 查询尚未过期的挑战。 */
    public Optional<MfaChallenge> find(String token) {
        String value = redisTemplate.opsForValue().get(challengeKey(token));
        if (value == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(objectMapper.readValue(value, MfaChallenge.class));
        } catch (JsonProcessingException exception) {
            delete(token);
            return Optional.empty();
        }
    }

    /** 记录一次错误动态码；超过上限时删除挑战。 */
    public boolean recordFailure(String token) {
        String attemptsKey = attemptsKey(token);
        Long attempts = redisTemplate.opsForValue().increment(attemptsKey);
        if (attempts != null && attempts == 1) {
            redisTemplate.expire(attemptsKey, properties.challengeTtl());
        }
        if (attempts != null && attempts >= properties.maxAttempts()) {
            delete(token);
            return false;
        }
        return true;
    }

    /** 消费成功或失效的挑战。 */
    public void delete(String token) {
        redisTemplate.delete(java.util.List.of(challengeKey(token), attemptsKey(token)));
    }

    /** 返回挑战有效秒数供前端倒计时。 */
    public long ttlSeconds() {
        return properties.challengeTtl().toSeconds();
    }

    private String challengeKey(String token) {
        return CHALLENGE_PREFIX + token;
    }

    private String attemptsKey(String token) {
        return ATTEMPTS_PREFIX + token;
    }
}
