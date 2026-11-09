package com.adpulse.system.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.adpulse.system.auth.mapper.AuthMapper;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** IP访问模式匹配测试。 */
@ExtendWith(MockitoExtension.class)
class IpAccessServiceTest {

    @Mock private AuthMapper authMapper;
    @InjectMocks private IpAccessService service;

    @Test
    void shouldAllowAnyIpWhenRuleIsDisabled() {
        UserAccount user = user(0);
        assertThat(service.isAllowed(user, "203.0.113.8")).isTrue();
    }

    @Test
    void shouldMatchIpv4CidrInWhitelistMode() {
        UserAccount user = user(2);
        when(authMapper.findAllowedIpCidrs(10L)).thenReturn(List.of("10.20.0.0/16"));

        assertThat(service.isAllowed(user, "10.20.3.9")).isTrue();
        assertThat(service.isAllowed(user, "10.21.3.9")).isFalse();
    }

    private UserAccount user(int mode) {
        UserAccount user = new UserAccount();
        user.setId(10L);
        user.setIpAccessMode(mode);
        return user;
    }
}
