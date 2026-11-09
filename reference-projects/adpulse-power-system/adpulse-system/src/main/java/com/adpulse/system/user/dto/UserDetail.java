package com.adpulse.system.user.dto;

import com.adpulse.system.user.model.UserAccount;
import java.util.List;
import java.util.Set;

/** 用户详情及所有系统管理关系。 */
public record UserDetail(
        UserAccount user,
        Set<String> roleIds,
        List<DepartmentScopeView> departmentScopes,
        Set<String> ipCidrs) {

    /** 用户部门数据范围响应项。 */
    public record DepartmentScopeView(String departmentId, boolean includeChildren) {}
}
