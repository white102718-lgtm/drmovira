package com.adpulse.system.feedback.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

/** 反馈提交与管理查询的权限边界测试。 */
class FeedbackAuthorizationTest {

    @Test
    void shouldAllowAuthenticatedSubmissionAndRequireManagerForCollection() {
        assertAuthority("create", "isAuthenticated()");
        assertAuthority("page", "hasAuthority('system:feedback:manage')");
        assertAuthority("summary", "hasAuthority('system:feedback:manage')");
        assertAuthority("detail", "hasAuthority('system:feedback:manage')");
        assertAuthority("updateStatus", "hasAuthority('system:feedback:manage')");
    }

    private void assertAuthority(String methodName, String expression) {
        Method method =
                Arrays.stream(FeedbackController.class.getDeclaredMethods())
                        .filter(candidate -> candidate.getName().equals(methodName))
                        .findFirst()
                        .orElseThrow();
        PreAuthorize annotation = method.getAnnotation(PreAuthorize.class);
        assertThat(annotation).isNotNull();
        assertThat(annotation.value()).isEqualTo(expression);
    }
}
