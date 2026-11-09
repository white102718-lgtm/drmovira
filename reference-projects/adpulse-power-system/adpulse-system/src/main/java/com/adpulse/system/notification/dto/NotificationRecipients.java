package com.adpulse.system.notification.dto;

import java.util.List;

/** 通知目标；人员、角色和部门可组合使用，最终收件人由服务端统一解析并去重。 */
public record NotificationRecipients(
        List<Long> userIds, List<Long> roleIds, List<Long> departmentIds) {
    public NotificationRecipients {
        userIds = userIds == null ? List.of() : List.copyOf(userIds);
        roleIds = roleIds == null ? List.of() : List.copyOf(roleIds);
        departmentIds = departmentIds == null ? List.of() : List.copyOf(departmentIds);
    }

    public static NotificationRecipients users(List<Long> userIds) {
        return new NotificationRecipients(userIds, List.of(), List.of());
    }

    public static NotificationRecipients roles(List<Long> roleIds) {
        return new NotificationRecipients(List.of(), roleIds, List.of());
    }

    public static NotificationRecipients departments(List<Long> departmentIds) {
        return new NotificationRecipients(List.of(), List.of(), departmentIds);
    }
}
