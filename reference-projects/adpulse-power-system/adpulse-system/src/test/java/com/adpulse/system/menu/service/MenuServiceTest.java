package com.adpulse.system.menu.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.menu.dto.UserMenuRoute;
import com.adpulse.system.menu.mapper.MenuMapper;
import com.adpulse.system.menu.model.Menu;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 当前用户角色菜单树和前端路由映射测试。 */
class MenuServiceTest {

    private final MenuMapper mapper = mock(MenuMapper.class);
    private final MenuService service = new MenuService(mapper);

    @Test
    void shouldIncludeDisabledMenusInManagementTree() {
        Menu disabledRoot = menu(1L, 0L, 1, "SYSTEM", "系统管理", null, null);
        disabledRoot.setStatus(0);
        Menu enabledChild =
                menu(2L, 1L, 2, "SYSTEM_USER", "用户管理", "/system/user", "system/user/list");
        enabledChild.setStatus(1);
        when(mapper.findAllNotDeleted()).thenReturn(List.of(disabledRoot, enabledChild));

        List<Menu> menus = service.tree();

        assertThat(menus).containsExactly(disabledRoot);
        assertThat(menus.getFirst().getStatus()).isZero();
        assertThat(menus.getFirst().getChildren()).containsExactly(enabledChild);
        verify(mapper).findAllNotDeleted();
    }

    @Test
    void shouldRejectGlobalMenuWritesByOrdinaryAdministrator() {
        var currentUser =
                new com.adpulse.system.common.security.CurrentUser(
                        7L, "session", "用户", java.util.Set.of());
        org.springframework.security.core.context.SecurityContextHolder.getContext()
                .setAuthentication(
                        new org.springframework.security.authentication
                                .UsernamePasswordAuthenticationToken(
                                currentUser, "", java.util.Set.of()));
        try {
            when(mapper.isMenuMaintenanceForbidden(7L)).thenReturn(true);
            org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.create(null))
                    .hasMessage("仅超级管理员可以维护全局菜单权限");
            org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.update(1L, null))
                    .hasMessage("仅超级管理员可以维护全局菜单权限");
            org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.delete(1L))
                    .hasMessage("仅超级管理员可以维护全局菜单权限");
            verify(mapper, org.mockito.Mockito.times(3)).isMenuMaintenanceForbidden(7L);
            org.mockito.Mockito.verifyNoMoreInteractions(mapper);
        } finally {
            org.springframework.security.core.context.SecurityContextHolder.clearContext();
        }
    }

    @Test
    void shouldBuildVbenRouteTreeForCurrentUser() {
        Menu root = menu(1L, 0L, 1, "SYSTEM", "系统管理", null, null);
        root.setIcon("lucide:shield-check");
        root.setSortOrder(10);
        Menu child = menu(2L, 1L, 2, "SYSTEM_USER", "用户管理", "/system/user", "system/user/list");
        child.setPermissionCode("system:user:list");
        child.setCacheable(1);
        when(mapper.findAuthorizedNavigationMenus(7L)).thenReturn(List.of(root, child));

        List<UserMenuRoute> routes = service.userMenuTree(7L);

        assertThat(routes).hasSize(1);
        UserMenuRoute rootRoute = routes.getFirst();
        assertThat(rootRoute.path()).isEqualTo("/system");
        assertThat(rootRoute.type()).isEqualTo("catalog");
        assertThat(rootRoute.children()).hasSize(1);
        UserMenuRoute childRoute = rootRoute.children().getFirst();
        assertThat(childRoute.component()).isEqualTo("/system/user/list");
        assertThat(childRoute.authCode()).isEqualTo("system:user:list");
        assertThat(childRoute.meta().keepAlive()).isTrue();
        verify(mapper).findAuthorizedNavigationMenus(7L);
    }

    @Test
    void shouldReturnWelcomeRouteWhenUserHasNoRoleMenus() {
        when(mapper.findAuthorizedNavigationMenus(8L)).thenReturn(List.of());

        List<UserMenuRoute> routes = service.userMenuTree(8L);

        assertThat(routes).hasSize(1);
        UserMenuRoute welcome = routes.getFirst();
        assertThat(welcome.name()).isEqualTo("Welcome");
        assertThat(welcome.path()).isEqualTo("/welcome");
        assertThat(welcome.component()).isEqualTo("/welcome/index");
        assertThat(welcome.meta().hideInMenu()).isTrue();
        verify(mapper).findAuthorizedNavigationMenus(8L);
    }

    @Test
    void shouldReturnWelcomeRouteWhenUserHasOnlyCatalogs() {
        Menu catalog =
                menu(1L, 0L, 1, "WORKBENCH", "工作台", "/workbench", "BasicLayout");
        when(mapper.findAuthorizedNavigationMenus(8L)).thenReturn(List.of(catalog));

        List<UserMenuRoute> routes = service.userMenuTree(8L);

        assertThat(routes)
                .singleElement()
                .extracting(UserMenuRoute::path)
                .isEqualTo("/welcome");
    }

    @Test
    void shouldRemoveBasicLayoutFromNestedCatalogs() {
        Menu root = menu(1L, 0L, 1, "SYSTEM", "系统管理", "/system", "BasicLayout");
        Menu integration =
                menu(2L, 1L, 1, "FEISHU_INTEGRATION", "飞书数据集成", "/system/feishu", "BasicLayout");
        Menu page =
                menu(
                        3L,
                        2L,
                        2,
                        "FEISHU_ORGANIZATION",
                        "组织架构同步",
                        "/system/feishu/organization",
                        "system/feishu-organization-sync");
        when(mapper.findAuthorizedNavigationMenus(9L)).thenReturn(List.of(root, integration, page));

        UserMenuRoute rootRoute = service.userMenuTree(9L).getFirst();
        UserMenuRoute integrationRoute = rootRoute.children().getFirst();

        assertThat(rootRoute.component()).isEqualTo("BasicLayout");
        assertThat(integrationRoute.component()).isNull();
        assertThat(integrationRoute.children().getFirst().component())
                .isEqualTo("/system/feishu-organization-sync");
    }

    private Menu menu(
            Long id,
            Long parentId,
            int menuType,
            String menuCode,
            String menuName,
            String routePath,
            String component) {
        Menu menu = new Menu();
        menu.setId(id);
        menu.setParentId(parentId);
        menu.setMenuType(menuType);
        menu.setMenuCode(menuCode);
        menu.setMenuName(menuName);
        menu.setRoutePath(routePath);
        menu.setComponent(component);
        menu.setVisible(1);
        menu.setCacheable(0);
        menu.setSortOrder(0);
        return menu;
    }
}
