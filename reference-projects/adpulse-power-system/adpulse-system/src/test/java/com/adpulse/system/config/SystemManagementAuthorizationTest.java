package com.adpulse.system.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.adpulse.system.application.controller.ApplicationDefinitionController;
import com.adpulse.system.department.controller.DepartmentController;
import com.adpulse.system.dictionary.controller.DictionaryController;
import com.adpulse.system.loginlog.controller.LoginLogController;
import com.adpulse.system.menu.controller.MenuController;
import com.adpulse.system.operationlog.controller.OperationLogController;
import com.adpulse.system.role.controller.RoleController;
import com.adpulse.system.user.controller.IpRuleController;
import com.adpulse.system.user.controller.UserController;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

class SystemManagementAuthorizationTest {

    @Test
    void shouldUsePageLevelPermissionForEveryActionInPageControllers() {
        assertClassAuthority(RoleController.class, "hasAuthority('system:role:list')");
        assertClassAuthority(IpRuleController.class, "hasAuthority('system:user:list')");
        assertClassAuthority(LoginLogController.class, "hasAuthority('system:user:list')");
        assertClassAuthority(OperationLogController.class, "hasAuthority('system:user:list')");
    }

    @Test
    void shouldAllowAuthenticatedDepartmentTreeLookupAndProtectDepartmentManagement() {
        assertThat(DepartmentController.class.getAnnotation(PreAuthorize.class).value())
                .isEqualTo("hasAuthority('system:department:list')");
        assertMethodAuthority(DepartmentController.class, "tree", "isAuthenticated()");
    }

    @Test
    void shouldAllowAuthenticatedUserLookupAndProtectUserManagement() {
        assertMethodAuthority(UserController.class, "page", "isAuthenticated()");
        assertMethodAuthority(UserController.class, "detail", "hasAuthority('system:user:list')");
        assertMethodAuthority(UserController.class, "create", "hasAuthority('system:user:list')");
        assertMethodAuthority(UserController.class, "update", "hasAuthority('system:user:list')");
        assertMethodAuthority(
                UserController.class, "resetPassword", "hasAuthority('system:user:list')");
        assertMethodAuthority(UserController.class, "resetMfa", "hasAuthority('system:user:list')");
        assertMethodAuthority(UserController.class, "delete", "hasAuthority('system:user:list')");
    }

    @Test
    void shouldUseMenuPagePermissionInsteadOfButtonPermissions() {
        assertMethodAuthority(MenuController.class, "tree", "hasAuthority('system:menu:list')");
        assertMethodAuthority(MenuController.class, "create", "hasAuthority('system:menu:list')");
        assertMethodAuthority(MenuController.class, "update", "hasAuthority('system:menu:list')");
        assertMethodAuthority(MenuController.class, "delete", "hasAuthority('system:menu:list')");
        assertMethodAuthority(MenuController.class, "currentUserMenus", "isAuthenticated()");
    }

    @Test
    void shouldProtectDictionaryManagementAndAllowAuthenticatedOptionLookup() {
        assertMethodAuthority(DictionaryController.class, "options", "isAuthenticated()");
        assertMethodAuthority(
                DictionaryController.class, "list", "hasAuthority('system:dictionary:list')");
        assertMethodAuthority(
                DictionaryController.class, "createType", "hasAuthority('system:dictionary:list')");
        assertMethodAuthority(
                DictionaryController.class, "createItem", "hasAuthority('system:dictionary:list')");
    }

    @Test
    void shouldProtectApplicationManagementActions() {
        String authority = "hasAnyAuthority('system:application:list', 'system:menu:list')";
        assertMethodAuthority(ApplicationDefinitionController.class, "managedList", authority);
        assertMethodAuthority(ApplicationDefinitionController.class, "create", authority);
        assertMethodAuthority(ApplicationDefinitionController.class, "update", authority);
        assertMethodAuthority(ApplicationDefinitionController.class, "delete", authority);
    }

    private static void assertClassAuthority(Class<?> controllerType, String expression) {
        PreAuthorize annotation = controllerType.getAnnotation(PreAuthorize.class);
        assertThat(annotation).isNotNull();
        assertThat(annotation.value()).isEqualTo(expression);
        assertThat(controllerType.getDeclaredMethods())
                .filteredOn(method -> method.getAnnotation(PreAuthorize.class) != null)
                .isEmpty();
    }

    private static void assertMethodAuthority(
            Class<?> controllerType, String methodName, String expression) {
        Method method =
                java.util.Arrays.stream(controllerType.getDeclaredMethods())
                        .filter(candidate -> candidate.getName().equals(methodName))
                        .findFirst()
                        .orElseThrow();
        PreAuthorize annotation = method.getAnnotation(PreAuthorize.class);
        assertThat(annotation).isNotNull();
        assertThat(annotation.value()).isEqualTo(expression);
    }
}
