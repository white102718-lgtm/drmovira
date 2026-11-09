package com.adpulse.system.operationlog.audit;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.application.controller.ApplicationDefinitionController;
import com.adpulse.system.department.controller.DepartmentController;
import com.adpulse.system.dictionary.controller.DictionaryController;
import com.adpulse.system.menu.controller.MenuController;
import com.adpulse.system.role.controller.RoleController;
import com.adpulse.system.user.controller.IpRuleController;
import com.adpulse.system.user.controller.UserController;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;

/** 系统管理写接口操作日志覆盖测试。 */
class OperationAuditCoverageTest {

    @Test
    void shouldRequireAuditAnnotationOnEveryManagementWriteEndpoint() {
        List<Class<?>> controllers =
                List.of(
                        UserController.class,
                        IpRuleController.class,
                        RoleController.class,
                        MenuController.class,
                        DepartmentController.class,
                        DictionaryController.class,
                        ApplicationDefinitionController.class);

        for (Class<?> controller : controllers) {
            for (Method method : controller.getDeclaredMethods()) {
                if (isWriteEndpoint(method)) {
                    OperationAudit audit = method.getAnnotation(OperationAudit.class);
                    assertThat(audit)
                            .as(controller.getSimpleName() + "#" + method.getName())
                            .isNotNull();
                    if (audit != null && !audit.targetIdParameter().isBlank()) {
                        assertThat(Arrays.stream(method.getParameters()).map(Parameter::getName))
                                .as(controller.getSimpleName() + "#" + method.getName())
                                .contains(audit.targetIdParameter());
                    }
                }
            }
        }
    }

    private boolean isWriteEndpoint(Method method) {
        return method.isAnnotationPresent(PostMapping.class)
                || method.isAnnotationPresent(PutMapping.class)
                || method.isAnnotationPresent(DeleteMapping.class);
    }
}
