package com.adpulse.system.user.mapper;

import com.adpulse.system.user.dto.DepartmentScopeRequest;
import com.adpulse.system.user.dto.UserDetail.DepartmentScopeView;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 用户及其系统管理关系持久化接口。 */
@Mapper
public interface UserMapper {
    List<UserAccount> findPage(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("departmentId") Long departmentId,
            @Param("roleId") Long roleId,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize);

    long count(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("departmentId") Long departmentId,
            @Param("roleId") Long roleId);

    UserAccount findById(@Param("id") Long id);

    /** 检查未删除用户的昵称占用情况，编辑时排除当前用户。 */
    boolean existsByEnglishNickname(
            @Param("englishNickname") String englishNickname, @Param("excludeId") Long excludeId);

    List<String> findDepartmentNames(@Param("userId") Long userId);

    String findDepartmentName(@Param("departmentId") Long departmentId);

    List<String> findRoleNames(@Param("userId") Long userId);

    /** 查询指定角色下仍启用的成员，用于人员离职通知收件人。 */
    List<Long> findActiveUserIdsByRoleName(@Param("roleName") String roleName);

    int insert(UserAccount user);

    int update(UserAccount user);

    /** 仅更新飞书用户的系统侧字段，避免覆盖同步维护的手机号和主部门。 */
    int updateFeishuLocalFields(UserAccount user);

    int updateProfile(UserAccount user);

    int updatePassword(
            @Param("id") Long id,
            @Param("passwordHash") String passwordHash,
            @Param("updatedBy") Long updatedBy);

    int resetMfa(@Param("id") Long id, @Param("updatedBy") Long updatedBy);

    int countActiveDepartment(@Param("departmentId") Long departmentId);

    int countActiveRoles(@Param("roleIds") Set<Long> roleIds);

    int countActiveDepartments(@Param("departmentIds") Set<Long> departmentIds);

    int countActiveGlobalIpRules();

    Set<Long> findRoleIds(@Param("userId") Long userId);

    List<DepartmentScopeView> findDepartmentScopes(@Param("userId") Long userId);

    Set<String> findPersonalIpCidrs(@Param("userId") Long userId);

    int softDeleteRoles(@Param("userId") Long userId, @Param("deletedAt") long deletedAt);

    int batchInsertRoles(
            @Param("userId") Long userId,
            @Param("roleIds") Set<Long> roleIds,
            @Param("createdBy") Long createdBy);

    int softDeleteScopes(@Param("userId") Long userId, @Param("deletedAt") long deletedAt);

    int batchInsertScopes(
            @Param("userId") Long userId,
            @Param("scopes") Set<DepartmentScopeRequest> scopes,
            @Param("createdBy") Long createdBy);

    int softDeletePersonalIps(@Param("userId") Long userId, @Param("deletedAt") long deletedAt);

    int batchInsertPersonalIps(
            @Param("userId") Long userId,
            @Param("cidrs") Set<String> cidrs,
            @Param("createdBy") Long createdBy);

    int softDelete(
            @Param("id") Long id,
            @Param("deletedAt") long deletedAt,
            @Param("updatedBy") Long updatedBy);
}
