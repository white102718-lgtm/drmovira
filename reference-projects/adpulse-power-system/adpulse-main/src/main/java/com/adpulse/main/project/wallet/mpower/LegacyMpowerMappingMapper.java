package com.adpulse.main.project.wallet.mpower;

import java.util.List;
import org.apache.ibatis.annotations.Param;

/** 老MPower组织数据只读查询；仅由临时钱包适配层使用。 */
public interface LegacyMpowerMappingMapper {
    /** 返回当前来源实例和库名，防止误连其他环境。 */
    SourceIdentity identity();

    /** 按租户及部门名称精确查询有效部门。 */
    List<LegacyDepartment> findDepartments(
            @Param("tenantId") Integer tenantId, @Param("departmentName") String departmentName);

    /** 按租户及用户名或昵称精确查询有效用户。 */
    List<LegacyUser> findUsers(
            @Param("tenantId") Integer tenantId, @Param("names") List<String> names);

    /** 老库实例标识。 */
    record SourceIdentity(String serverUuid, String schemaName) {}

    /** 老库部门候选项。 */
    record LegacyDepartment(String departmentId, String departmentName) {}

    /** 老库用户候选项。 */
    record LegacyUser(String userId, String userName, String nickName) {}
}
