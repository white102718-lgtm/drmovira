package com.adpulse.system.auth.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.auth.model.ServerSession;
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** Redis会话角色到Spring Security权限的映射测试。 */
class JwtSessionFilterRoleAuthorityTest {

    @Test
    void shouldExposeRoleCodesWithSpringSecurityRolePrefix() {
        ServerSession session =
                new ServerSession(
                        "session",
                        9L,
                        "测试用户",
                        null,
                        null,
                        null,
                        null,
                        Set.of(1L),
                        Set.of("AM"),
                        Set.of("客户经理"),
                        "127.0.0.1",
                        Set.of("task:list"),
                        Instant.now());

        assertThat(JwtSessionFilter.createAuthorities(session))
                .extracting(authority -> authority.getAuthority())
                .containsExactlyInAnyOrder("task:list", "ROLE_AM");
    }
}
