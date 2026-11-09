package com.adpulse.main.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 主业务服务共享会话用户校验测试。 */
@ExtendWith(MockitoExtension.class)
class MainSessionUserValidatorTest {

    @Mock private MainUserAccessMapper mapper;

    @Test
    void shouldAcceptActiveUserWithoutIpRestriction() {
        when(mapper.findActiveUser(1L))
                .thenReturn(new MainUserAccessMapper.MainUserAccess(1L, "测试用户", 1));

        var result = new MainSessionUserValidator(mapper).validate(1L, "127.0.0.1");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().displayName()).isEqualTo("测试用户");
    }

    @Test
    void shouldRejectRestrictedUserOutsideIpRules() {
        when(mapper.findActiveUser(1L))
                .thenReturn(new MainUserAccessMapper.MainUserAccess(1L, "测试用户", 2));
        when(mapper.findAllowedIpCidrs(1L)).thenReturn(List.of("10.0.0.0/8"));

        var result = new MainSessionUserValidator(mapper).validate(1L, "192.168.1.1");

        assertThat(result).isEmpty();
    }
}
