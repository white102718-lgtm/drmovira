package com.adpulse.main.project.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 代理线持久化模型。 */
@Data
public class AgencyLine {
    private Long id;
    private Long projectId;
    private String requestId;
    private String lineName;

    /** 项目内业务状态，不控制媒体广告：active进行中，stopped已停投。 */
    private String status;

    private String platformValue;
    private String type;
    private String deliveryUrl;
    private String pageId;
    private String pixelName;
    private String pixelId;
    private String tokenCiphertext;
    private String testCode;
    private String cloakUrl;
    private Long optimizerId;
    private String optimizerName;

    /** 查询时关联的当前用户状态；未分配或用户已删除时为空。 */
    private Integer optimizerStatus;

    private Long createdBy;
    private Long updatedBy;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
