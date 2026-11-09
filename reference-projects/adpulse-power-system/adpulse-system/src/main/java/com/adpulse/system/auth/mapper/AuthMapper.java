package com.adpulse.system.auth.mapper;

import com.adpulse.system.user.model.UserAccount;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 认证所需用户、权限和IP数据查询。 */
@Mapper
public interface AuthMapper {

    UserAccount findLoginUser(@Param("phone") String phone);

    UserAccount findFeishuLoginUser(
            @Param("tenantKey") String tenantKey,
            @Param("openId") String openId,
            @Param("unionId") String unionId);

    UserAccount findActiveUserById(@Param("userId") Long userId);

    List<String> findPermissionCodes(@Param("userId") Long userId);

    /** 查询用户当前生效的菜单编码，并补齐有效父级菜单。 */
    List<String> findMenuCodes(@Param("userId") Long userId);

    String findPrimaryDepartmentName(@Param("departmentId") Long departmentId);

    List<UserRoleView> findActiveRoles(@Param("userId") Long userId);

    List<String> findAllowedIpCidrs(@Param("userId") Long userId);

    int recordLoginSuccess(
            @Param("userId") Long userId,
            @Param("loginAt") LocalDateTime loginAt,
            @Param("loginIp") String loginIp);

    int incrementLoginFailure(@Param("userId") Long userId);

    int bindMfa(
            @Param("userId") Long userId,
            @Param("secretCiphertext") String secretCiphertext,
            @Param("boundAt") LocalDateTime boundAt,
            @Param("counter") long counter);

    int recordMfaCounter(@Param("userId") Long userId, @Param("counter") long counter);

    /** 登录会话所需的有效角色摘要。 */
    record UserRoleView(Long id, String roleCode, String roleName) {}
}
