package com.adpulse.system.config;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** 首次启动管理员所需的最小持久化操作。 */
@Mapper
public interface BootstrapMapper {

    @Select("SELECT COUNT(*) FROM sys_user WHERE deleted_at = 0")
    int countActiveUsers();

    @Select("SELECT id FROM sys_role WHERE role_code = 'ADMIN' AND deleted_at = 0 LIMIT 1")
    Long findAdminRoleId();

    @Insert(
            """
            INSERT INTO sys_user (
                username, phone, password_hash, display_name, english_nickname,
                status, ip_access_mode, password_changed_at, mfa_status
            ) VALUES (
                #{username}, #{phone}, #{passwordHash}, #{displayName},
                #{englishNickname}, 1, 0, CURRENT_TIMESTAMP(3), -1
            )
            """)
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insertUser(BootstrapUser user);

    @Insert("INSERT INTO sys_user_role (user_id, role_id) VALUES (#{userId}, #{roleId})")
    int insertUserRole(@Param("userId") Long userId, @Param("roleId") Long roleId);

    /** 首次管理员插入参数。 */
    class BootstrapUser {
        public Long id;
        public String username;
        public String phone;
        public String passwordHash;
        public String displayName;
        public String englishNickname;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }
    }
}
