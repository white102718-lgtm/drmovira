package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 九类可入库资源的统一资产记录，覆盖广告社媒资源与办公资产。 */
@Data
public class MediaAsset {
    private Long id;
    private String assetType;
    private String assetName;
    private String assetCode;
    private String projectId;
    private String projectName;
    private String channelId;
    private String channelName;
    private String secretData;
    private String status;
    private Long assigneeId;
    private String assigneeName;

    /** 像素分配时固化的申请表所选使用团队；结项释放后清空。 */
    private String usageTeam;

    /** 使用人的当前主部门名称；由组织架构实时推导，资产录入和导入均不可手工写入。 */
    private String assigneeDepartmentName;

    /** 多使用人的当前主部门名称，由组织架构实时推导。 */
    private String usageDepartmentNames;

    /** 广告账户和像素由共享分配关系汇总出的全部使用人名称，其他资产类型为空。 */
    private String usageUserNames;

    /** 像素共享使用关系汇总出的用户 ID，使用英文逗号分隔，供编辑页回填。 */
    private String usageUserIds;

    private Long applicationId;
    private String remark;
    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
