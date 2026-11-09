package com.adpulse.system.auth.service;

import com.adpulse.system.auth.model.ServerSession;
import com.adpulse.system.config.SecurityProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** Redis 服务端会话存储。 */
@Component
public class SessionStore {

    private static final String SESSION_PREFIX = "adpulse:session:";
    private static final String USER_SESSIONS_PREFIX = "adpulse:user-sessions:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final SecurityProperties properties;

    public SessionStore(
            StringRedisTemplate redisTemplate,
            ObjectMapper objectMapper,
            SecurityProperties properties) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    /** 保存会话，并登记用户到会话的反向索引。 */
    public void save(ServerSession session) {
        try {
            String key = sessionKey(session.sessionId());
            String value = objectMapper.writeValueAsString(session);
            redisTemplate
                    .opsForValue()
                    .set(key, value, properties.sessionTtl().toMillis(), TimeUnit.MILLISECONDS);
            String userKey = userSessionsKey(session.userId());
            redisTemplate.opsForSet().add(userKey, session.sessionId());
            redisTemplate.expire(userKey, properties.sessionTtl().plusHours(1));
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("无法序列化登录会话", exception);
        }
    }

    /** 查询有效会话。 */
    public Optional<ServerSession> find(String sessionId) {
        String value = redisTemplate.opsForValue().get(sessionKey(sessionId));
        if (value == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(objectMapper.readValue(value, ServerSession.class));
        } catch (JsonProcessingException exception) {
            delete(sessionId, null);
            return Optional.empty();
        }
    }

    /** 删除单个会话。 */
    public void delete(String sessionId, Long userId) {
        redisTemplate.delete(sessionKey(sessionId));
        if (userId != null) {
            redisTemplate.opsForSet().remove(userSessionsKey(userId), sessionId);
        }
    }

    /** 撤销指定用户的全部登录会话。 */
    public void revokeUser(Long userId) {
        String userKey = userSessionsKey(userId);
        Set<String> sessionIds = redisTemplate.opsForSet().members(userKey);
        if (sessionIds != null && !sessionIds.isEmpty()) {
            redisTemplate.delete(sessionIds.stream().map(this::sessionKey).toList());
        }
        redisTemplate.delete(userKey);
    }

    private String sessionKey(String sessionId) {
        return SESSION_PREFIX + sessionId;
    }

    private String userSessionsKey(Long userId) {
        return USER_SESSIONS_PREFIX + userId;
    }
}
