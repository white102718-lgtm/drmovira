package com.adpulse.system.menu.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.menu.dto.MenuSaveRequest;
import com.adpulse.system.menu.dto.UserMenuRoute;
import com.adpulse.system.menu.mapper.MenuMapper;
import com.adpulse.system.menu.model.Menu;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 菜单树与按钮权限资源管理服务。 */
@Service
public class MenuService {

    private final MenuMapper mapper;

    public MenuService(MenuMapper mapper) {
        this.mapper = mapper;
    }

    /** 查询完整菜单权限树。 */
    public List<Menu> tree() {
        return buildTree(mapper.findAllNotDeleted());
    }

    /** 查询指定登录用户通过有效角色获得的前端导航菜单树。 */
    public List<UserMenuRoute> userMenuTree(Long userId) {
        List<Menu> authorizedMenus = mapper.findAuthorizedNavigationMenus(userId);
        boolean hasAccessiblePage =
                authorizedMenus.stream().anyMatch(menu -> menu.getMenuType() == 2);
        if (!hasAccessiblePage) {
            return List.of(welcomeRoute());
        }
        return buildTree(authorizedMenus).stream()
                .map(menu -> toUserRoute(menu, 0))
                .toList();
    }

    /** 没有任何菜单权限时提供稳定空状态，避免登录后进入无权限页或 404。 */
    private UserMenuRoute welcomeRoute() {
        return new UserMenuRoute(
                "0",
                "",
                "Welcome",
                "/welcome",
                "/welcome/index",
                "",
                "menu",
                new UserMenuRoute.Meta("欢迎", null, 0, true, false, null),
                List.of());
    }

    private List<Menu> buildTree(List<Menu> menus) {
        Map<Long, Menu> index = new LinkedHashMap<>();
        menus.forEach(
                menu -> {
                    menu.setChildren(new ArrayList<>());
                    index.put(menu.getId(), menu);
                });
        List<Menu> roots = new ArrayList<>();
        for (Menu menu : menus) {
            Menu parent = index.get(menu.getParentId());
            if (menu.getParentId() == 0 || parent == null) {
                roots.add(menu);
            } else {
                parent.getChildren().add(menu);
            }
        }
        return roots;
    }

    private UserMenuRoute toUserRoute(Menu menu, int depth) {
        String path =
                StringUtils.hasText(menu.getRoutePath())
                        ? menu.getRoutePath()
                        : "/" + menu.getMenuCode().toLowerCase(Locale.ROOT).replace('_', '-');
        String component =
                menu.getMenuType() == 1 && depth > 0
                        ? null
                        : normalizeComponent(menu.getComponent());
        UserMenuRoute.Meta meta =
                new UserMenuRoute.Meta(
                        menu.getMenuName(),
                        menu.getIcon(),
                        menu.getSortOrder(),
                        menu.getVisible() != null && menu.getVisible() == 0,
                        menu.getCacheable() != null && menu.getCacheable() == 1,
                        menu.getExternalLink());
        return new UserMenuRoute(
                menu.getId().toString(),
                menu.getParentId() == 0 ? "" : menu.getParentId().toString(),
                menu.getMenuCode(),
                path,
                component,
                menu.getPermissionCode() == null ? "" : menu.getPermissionCode(),
                menu.getMenuType() == 1 ? "catalog" : "menu",
                meta,
                menu.getChildren().stream().map(child -> toUserRoute(child, depth + 1)).toList());
    }

    private String normalizeComponent(String component) {
        if (!StringUtils.hasText(component)
                || component.startsWith("/")
                || "BasicLayout".equals(component)
                || "IFrameView".equals(component)) {
            return component;
        }
        return "/" + component;
    }

    /** 新增菜单或按钮资源，超级管理员和 ADMIN 角色均可操作。 */
    @Transactional
    public Menu create(MenuSaveRequest request) {
        requireMenuMaintenanceAllowed(true);
        validateParent(null, request);
        Menu menu = new Menu();
        apply(menu, request);
        Long operatorId = SecurityContextHelper.currentUserId();
        menu.setCreatedBy(operatorId);
        menu.setUpdatedBy(operatorId);
        mapper.insert(menu);
        return mapper.findById(menu.getId());
    }

    /** 修改菜单并防止形成树环。 */
    @Transactional
    public Menu update(Long id, MenuSaveRequest request) {
        requireMenuMaintenanceAllowed(false);
        Menu menu = requireMenu(id);
        validateParent(menu, request);
        apply(menu, request);
        menu.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.update(menu);
        return mapper.findById(id);
    }

    /** 软删除叶子菜单并同步软删除角色授权。 */
    @Transactional
    public void delete(Long id) {
        requireMenuMaintenanceAllowed(false);
        requireMenu(id);
        if (mapper.countChildren(id) > 0) {
            throw BusinessException.conflict("请先删除或移动子菜单");
        }
        long deletedAt = System.currentTimeMillis();
        mapper.softDeleteRoleRelations(id, deletedAt);
        mapper.softDelete(id, deletedAt, SecurityContextHelper.currentUserId());
    }

    private void requireMenuMaintenanceAllowed(boolean allowAdminCreate) {
        var currentUser = SecurityContextHelper.currentUser();
        boolean isAdmin =
                currentUser.authorities().stream()
                        .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority()));
        if (allowAdminCreate && isAdmin) {
            return;
        }
        if (mapper.isMenuMaintenanceForbidden(currentUser.userId())) {
            String message =
                    allowAdminCreate
                            ? "仅超级管理员或ADMIN角色可以新增全局菜单权限"
                            : "仅超级管理员可以维护全局菜单权限";
            throw BusinessException.conflict(message);
        }
    }

    private Menu requireMenu(Long id) {
        Menu menu = mapper.findById(id);
        if (menu == null) {
            throw BusinessException.notFound("菜单");
        }
        return menu;
    }

    private void validateParent(Menu current, MenuSaveRequest request) {
        if (request.parentId() == 0) {
            if (request.menuType() == 3) {
                throw BusinessException.conflict("按钮权限不能作为根节点");
            }
            return;
        }
        Menu parent = requireMenu(request.parentId());
        if (current != null && parent.getId().equals(current.getId())) {
            throw BusinessException.conflict("菜单不能以自身为父节点");
        }
        if (parent.getMenuType() == 3) {
            throw BusinessException.conflict("按钮资源下不能创建子节点");
        }
        if (request.menuType() == 3 && parent.getMenuType() != 2) {
            throw BusinessException.conflict("按钮权限必须挂在菜单下");
        }
        if (current != null && isDescendant(parent.getId(), current.getId())) {
            throw BusinessException.conflict("菜单不能移动到自身子树下");
        }
    }

    private boolean isDescendant(Long candidateId, Long ancestorId) {
        Long cursor = candidateId;
        while (cursor != 0) {
            Menu menu = mapper.findById(cursor);
            if (menu == null) {
                return false;
            }
            if (menu.getParentId().equals(ancestorId)) {
                return true;
            }
            cursor = menu.getParentId();
        }
        return false;
    }

    private void apply(Menu menu, MenuSaveRequest request) {
        menu.setParentId(request.parentId());
        menu.setMenuType(request.menuType());
        menu.setMenuCode(request.menuCode());
        menu.setMenuName(request.menuName());
        menu.setRoutePath(request.routePath());
        menu.setComponent(request.component());
        menu.setIcon(request.icon());
        menu.setPermissionCode(
                StringUtils.hasText(request.permissionCode())
                        ? request.permissionCode().trim()
                        : null);
        menu.setVisible(request.visible());
        menu.setCacheable(request.cacheable());
        menu.setExternalLink(request.externalLink());
        menu.setSortOrder(request.sortOrder() == null ? 0 : request.sortOrder());
        menu.setStatus(request.status());
        menu.setRemark(request.remark());
    }
}
