package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 资产申请流程评论。 */
@Data
public class AssetApplicationComment {
    private Long id;
    private Long applicationId;
    private Long actorId;
    private String actorName;
    private String actorRole;
    private String content;
    private LocalDateTime createdAt;
}
