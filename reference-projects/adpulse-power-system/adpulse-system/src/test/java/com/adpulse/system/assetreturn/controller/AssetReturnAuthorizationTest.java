package com.adpulse.system.assetreturn.controller;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

/** 资产回收接口权限配置测试。 */
class AssetReturnAuthorizationTest {

    @Test
    void shouldAllowAssigneeRequestAndRequireManagerForProcessing() {
        assertAuthority("create", "isAuthenticated()");
        assertAuthority("page", "hasAuthority('media:resource:return:manage')");
        assertAuthority("summary", "hasAuthority('media:resource:return:manage')");
        assertAuthority("complete", "hasAuthority('media:resource:return:manage')");
    }

    private void assertAuthority(String methodName, String expression) {
        Method method =
                Arrays.stream(AssetReturnController.class.getDeclaredMethods())
                        .filter(candidate -> candidate.getName().equals(methodName))
                        .findFirst()
                        .orElseThrow();
        PreAuthorize annotation = method.getAnnotation(PreAuthorize.class);
        assertThat(annotation).isNotNull();
        assertThat(annotation.value()).isEqualTo(expression);
    }
}
