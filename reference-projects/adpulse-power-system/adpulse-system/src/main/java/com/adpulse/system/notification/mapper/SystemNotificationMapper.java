package com.adpulse.system.notification.mapper;

import com.adpulse.system.notification.model.SiteNotificationRecord;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/** 统一通知收件人解析及站内消息写入接口。 */
@Mapper
public interface SystemNotificationMapper {
    List<Long> findActiveUserIds(@Param("userIds") List<Long> userIds);

    List<Long> findActiveUserIdsByRoles(@Param("roleIds") List<Long> roleIds);

    /** 部门通知仅匹配用户主部门，避免将数据权限范围误作为组织成员关系。 */
    List<Long> findActiveUserIdsByDepartments(@Param("departmentIds") List<Long> departmentIds);

    int insertNotification(SiteNotificationRecord notification);

    List<SiteNotificationRecord> findNotificationsAfter(
            @Param("userId") Long userId,
            @Param("lastEventId") Long lastEventId,
            @Param("limit") int limit);

    Long findLatestNotificationId(@Param("userId") Long userId);
}
