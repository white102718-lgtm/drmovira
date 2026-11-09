package com.adpulse.system.feishuorg.model;

import java.util.List;

/** 飞书通讯录一次完整读取形成的不可变快照。 */
public record FeishuOrganizationSnapshot(
        String tenantKey, List<DepartmentRecord> departments, List<UserRecord> users) {

    /** 飞书部门快照。 */
    public record DepartmentRecord(
            String departmentId,
            String parentDepartmentId,
            String name,
            int order,
            String leaderUserId) {}

    /** 飞书人员快照。 */
    public record UserRecord(
            String userId,
            String openId,
            String unionId,
            String name,
            String mobile,
            String email,
            String avatarUrl,
            boolean active,
            List<String> departmentIds) {}
}
