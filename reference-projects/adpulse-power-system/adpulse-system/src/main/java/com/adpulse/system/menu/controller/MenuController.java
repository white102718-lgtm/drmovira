package com.adpulse.system.menu.controller;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.menu.dto.MenuSaveRequest;
import com.adpulse.system.menu.dto.UserMenuRoute;
import com.adpulse.system.menu.model.Menu;
import com.adpulse.system.menu.service.MenuService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 菜单和按钮权限管理接口。 */
@RestController
@RequestMapping("/menus")
@Tag(name = "菜单管理", description = "目录、菜单和按钮权限维护")
public class MenuController {

    private final MenuService service;

    public MenuController(MenuService service) {
        this.service = service;
    }

    /** 返回当前登录用户通过角色获得的前端导航菜单。 */
    @GetMapping({"", "/"})
    @PreAuthorize("isAuthenticated()")
    public ApiResponse<List<UserMenuRoute>> currentUserMenus() {
        return ApiResponse.success(service.userMenuTree(SecurityContextHelper.currentUserId()));
    }

    @GetMapping("/tree")
    @PreAuthorize("hasAuthority('system:menu:list')")
    public ApiResponse<List<Menu>> tree() {
        return ApiResponse.success(service.tree());
    }

    @PostMapping
    @PreAuthorize("hasAuthority('system:menu:list')")
    @OperationAudit(
            module = "MENU",
            type = OperationType.CREATE,
            name = "新增菜单",
            targetType = "sys_menu")
    public ApiResponse<Menu> create(@Valid @RequestBody MenuSaveRequest request) {
        return ApiResponse.success(service.create(request));
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasAuthority('system:menu:list')")
    @OperationAudit(
            module = "MENU",
            type = OperationType.UPDATE,
            name = "修改菜单",
            targetType = "sys_menu",
            targetIdParameter = "id")
    public ApiResponse<Menu> update(
            @PathVariable Long id, @Valid @RequestBody MenuSaveRequest request) {
        return ApiResponse.success(service.update(id, request));
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('system:menu:list')")
    @OperationAudit(
            module = "MENU",
            type = OperationType.DELETE,
            name = "删除菜单",
            targetType = "sys_menu",
            targetIdParameter = "id")
    public ApiResponse<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ApiResponse.success();
    }
}
