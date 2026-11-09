package com.adpulse.main.adaccountasset;

import java.time.LocalDateTime;
import lombok.Data;

/** 广告账户文件导入记录；失败工作簿只能以加密内容持久化。 */
@Data
public class AdAccountImportLog {
    private Long id;
    private String fileName;
    private int totalCount;
    private int successCount;
    private int failureCount;
    private String failureDetails;
    private String failedFileCiphertext;
    private Long operatorId;
    private LocalDateTime createdAt;
}
