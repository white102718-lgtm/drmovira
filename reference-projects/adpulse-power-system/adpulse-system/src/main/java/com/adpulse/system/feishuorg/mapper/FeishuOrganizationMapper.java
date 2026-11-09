package com.adpulse.system.feishuorg.mapper;

import com.adpulse.system.department.model.Department;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncLog;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSyncLog;
import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 飞书组织同步专用持久化接口，不维护角色及数据权限关系。 */
@Mapper
public interface FeishuOrganizationMapper {

    FeishuApplicationConfig findApplicationConfig();

    /** 查询仍可接收飞书应用私聊的启用用户 open_id。 */
    List<String> findActiveFeishuOpenIds(@Param("userIds") List<Long> userIds);

    /** 按手机号查询指定测试收件人的飞书 open_id。 */
    List<String> findActiveFeishuOpenIdsByPhone(@Param("phone") String phone);

    /** 查询可接收 Mpower 机器人通知的启用用户手机号。 */
    List<String> findActiveUserPhones(@Param("userIds") List<Long> userIds);

    int insertApplicationConfig(FeishuApplicationConfig config);

    int updateApplicationConfig(FeishuApplicationConfig config);

    List<SyncLog> findLogs();

    List<Department> findDepartments(@Param("tenantKey") String tenantKey);

    List<UserAccount> findUsers(@Param("tenantKey") String tenantKey);

    int insertDepartment(Department department);

    int updateDepartment(Department department);

    int disableMissingDepartments(
            @Param("tenantKey") String tenantKey,
            @Param("externalIds") List<String> externalIds,
            @Param("updatedBy") Long updatedBy);

    int insertUser(UserAccount user);

    int updateUser(UserAccount user);

    int updateDepartmentLeader(
            @Param("departmentId") Long departmentId,
            @Param("leaderUserId") Long leaderUserId,
            @Param("updatedBy") Long updatedBy);

    List<Long> findMissingActiveUserIds(
            @Param("tenantKey") String tenantKey, @Param("externalIds") List<String> externalIds);

    int disableUsers(@Param("ids") List<Long> ids, @Param("updatedBy") Long updatedBy);

    int insertLog(FeishuOrganizationSyncLog log);

    int finishLog(FeishuOrganizationSyncLog log);
}
