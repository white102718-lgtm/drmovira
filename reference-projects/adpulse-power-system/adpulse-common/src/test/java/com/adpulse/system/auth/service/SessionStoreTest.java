package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.auth.model.ServerSession;
import com.adpulse.system.config.SecurityProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

/** 验证会话真实姓名的 Redis 存取及旧会话兼容性。 */
class SessionStoreTest {

    private final StringRedisTemplate redis = mock(StringRedisTemplate.class);
    private final ValueOperations<String, String> values = mock(ValueOperations.class);
    private final SetOperations<String, String> sets = mock(SetOperations.class);
    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();
    private final SessionStore store =
            new SessionStore(
                    redis,
                    objectMapper,
                    new SecurityProperties("test-secret", "test", Duration.ofHours(8)));

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = "张三")
    void shouldRoundTripRealName(String realName) throws Exception {
        when(redis.opsForValue()).thenReturn(values);
        when(redis.opsForSet()).thenReturn(sets);
        ServerSession session =
                new ServerSession(
                        "session",
                        9L,
                        "昵称",
                        "English",
                        realName,
                        null,
                        null,
                        Set.of(),
                        Set.of(),
                        Set.of(),
                        "127.0.0.1",
                        Set.of(),
                        Instant.now());

        store.save(session);

        ArgumentCaptor<String> json = ArgumentCaptor.forClass(String.class);
        verify(values)
                .set(
                        eq("adpulse:session:session"),
                        json.capture(),
                        eq(28800000L),
                        eq(TimeUnit.MILLISECONDS));
        assertThat(objectMapper.readTree(json.getValue()).has("realName")).isTrue();
        when(values.get("adpulse:session:session")).thenReturn(json.getValue());
        assertThat(store.find("session")).contains(session);
    }

    @Test
    void shouldReadLegacySessionWithoutRealName() {
        when(redis.opsForValue()).thenReturn(values);
        when(values.get("adpulse:session:legacy"))
                .thenReturn(
                        """
                        {"sessionId":"legacy","userId":9,"displayName":"昵称",
                         "englishNickname":"English","permissions":["task:list"]}
                        """);

        ServerSession session = store.find("legacy").orElseThrow();

        assertThat(session.realName()).isNull();
        assertThat(session.displayName()).isEqualTo("昵称");
        assertThat(session.englishNickname()).isEqualTo("English");
        assertThat(session.permissions()).containsExactly("task:list");
    }
}
