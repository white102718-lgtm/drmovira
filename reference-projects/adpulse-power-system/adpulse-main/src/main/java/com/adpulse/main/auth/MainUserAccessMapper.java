package com.adpulse.main.auth;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** 主业务服务读取系统用户访问状态的持久化接口。 */
@Mapper
public interface MainUserAccessMapper {

    /** 查询当前有效用户的认证摘要。 */
    @Select(
            """
            SELECT id, display_name, ip_access_mode
            FROM sys_user
            WHERE id = #{userId} AND status = 1 AND deleted_at = 0
            """)
    MainUserAccess findActiveUser(@Param("userId") Long userId);

    /** 查询用户可使用的全局及个人IP白名单。 */
    @Select(
            """
            SELECT ip_cidr
            FROM sys_ip_rule
            WHERE status = 1
              AND deleted_at = 0
              AND (scope_type = 1 OR (scope_type = 2 AND user_id = #{userId}))
            """)
    List<String> findAllowedIpCidrs(@Param("userId") Long userId);

    /** 主业务认证所需的用户摘要。 */
    record MainUserAccess(Long id, String displayName, Integer ipAccessMode) {}
}
