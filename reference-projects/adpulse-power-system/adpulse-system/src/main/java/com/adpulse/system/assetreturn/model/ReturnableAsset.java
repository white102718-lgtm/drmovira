package com.adpulse.system.assetreturn.model;

import lombok.Data;

/** 回收流程内部使用的已分配资产快照。 */
@Data
public class ReturnableAsset {
    private Long id;
    private String assetType;
    private String assetName;
    private String assetCode;
    private String projectId;
    private String projectName;
    private String channelId;
    private String channelName;
    private String status;
    private Long assigneeId;
    private String assigneeName;
    private Long applicationId;
}
