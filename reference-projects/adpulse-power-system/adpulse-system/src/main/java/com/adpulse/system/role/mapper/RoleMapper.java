package com.adpulse.system.role.mapper;

import com.adpulse.system.role.model.Role;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 角色及角色菜单关系持久化接口。 */
@Mapper
public interface RoleMapper {
    /** 其他人不能通过共享角色修改超级管理员的角色或菜单授权。 */
    boolean hasOtherSuperAdminUser(
            @Param("roleId") Long roleId, @Param("operatorId") Long operatorId);

    List<Role> findPage(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long count(@Param("keyword") String keyword, @Param("status") Integer status);

    Role findById(@Param("id") Long id);

    int insert(Role role);

    int update(Role role);

    Set<Long> findMenuIds(@Param("roleId") Long roleId);

    int countActiveMenus(@Param("menuIds") Set<Long> menuIds);

    int softDeleteMenuRelations(@Param("roleId") Long roleId, @Param("deletedAt") long deletedAt);

    int batchInsertMenus(
            @Param("roleId") Long roleId,
            @Param("menuIds") Set<Long> menuIds,
            @Param("createdBy") Long createdBy);

    int countUsers(@Param("roleId") Long roleId);

    int softDelete(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}
