package com.adpulse.system.asset.model;

import java.time.LocalDateTime;
import lombok.Data;

/** 资产 Excel 导入的持久化记录；失败工作簿仅保存加密内容。 */
@Data
public class AssetImportLog {
    private Long id;
    private String assetSubtype;
    private String fileName;
    private int totalCount;
    private int successCount;
    private int failureCount;
    private String failureDetails;
    private String failedFileCiphertext;
    private Long operatorId;
    private LocalDateTime createdAt;
}
