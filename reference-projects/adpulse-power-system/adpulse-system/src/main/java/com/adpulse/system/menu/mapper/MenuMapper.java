package com.adpulse.system.menu.mapper;

import com.adpulse.system.menu.model.Menu;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 菜单持久化访问接口。 */
@Mapper
public interface MenuMapper {
    /** 已启用超级管理员保护时，仅超级管理员可维护全局菜单资源。 */
    boolean isMenuMaintenanceForbidden(@Param("operatorId") Long operatorId);

    /** 查询全部未删除的菜单资源，供菜单管理树展示并恢复停用菜单。 */
    List<Menu> findAllNotDeleted();

    List<Menu> findAuthorizedNavigationMenus(@Param("userId") Long userId);

    Menu findById(@Param("id") Long id);

    int insert(Menu menu);

    int update(Menu menu);

    int countChildren(@Param("id") Long id);

    int softDelete(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);

    int softDeleteRoleRelations(@Param("menuId") Long menuId, @Param("deletedAt") long deletedAt);
}
