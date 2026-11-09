package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.UserDepartment;
import com.adpulse.main.adaccountasset.AdAccountAssetModels.ActiveUser;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 广告户使用人所属部门查询。
 *
 * <p>部门由使用人的当前主部门实时推导，人员调岗后列表同步展示新部门。
 */
@Mapper
public interface AdAccountUserMapper {

    /** 查询全部有效用户，供 Excel 导入一次性建立显示名称索引。 */
    @Select(
            """
            SELECT usage_user.id AS userId,
                   COALESCE(NULLIF(usage_user.real_name, ''), NULLIF(usage_user.display_name, ''), usage_user.username) AS displayName,
                   department.dept_name AS departmentName
            FROM sys_user usage_user
            LEFT JOIN sys_department department
              ON department.id = usage_user.primary_department_id
             AND department.deleted_at = 0
            WHERE usage_user.status = 1
              AND usage_user.deleted_at = 0
            ORDER BY usage_user.id
            """)
    List<ActiveUser> findAllActiveUsers();

    /** 查询有效用户的稳定显示名称。 */
    @Select(
            """
            SELECT COALESCE(NULLIF(real_name, ''), NULLIF(display_name, ''), username)
            FROM sys_user
            WHERE id = #{userId}
              AND status = 1
              AND deleted_at = 0
            """)
    String findDisplayName(@Param("userId") Long userId);

    /** 查询生命周期操作者名称；用户停用或软删除后仍保留其历史身份。 */
    @Select(
            """
            SELECT COALESCE(NULLIF(real_name, ''), NULLIF(display_name, ''), username)
            FROM sys_user
            WHERE id = #{userId}
            """)
    String findHistoricalDisplayName(@Param("userId") Long userId);

    @Select(
            """
            SELECT department.dept_name
            FROM sys_user usage_user
            JOIN sys_department department
              ON department.id = usage_user.primary_department_id
             AND department.deleted_at = 0
            WHERE usage_user.id = #{userId}
              AND usage_user.deleted_at = 0
            """)
    String findCurrentDepartmentName(@Param("userId") Long userId);

    /** 批量查询使用人的当前主部门，供广告账户列表一次性装配展示字段。 */
    @Select(
            """
            <script>
            SELECT usage_user.id AS userId, department.dept_name AS departmentName
            FROM sys_user usage_user
            JOIN sys_department department
              ON department.id = usage_user.primary_department_id
             AND department.deleted_at = 0
            WHERE usage_user.deleted_at = 0
              AND usage_user.id IN
              <foreach collection="userIds" item="userId" open="(" separator="," close=")">
                #{userId}
              </foreach>
            </script>
            """)
    List<UserDepartment> findCurrentDepartments(@Param("userIds") List<Long> userIds);
}
