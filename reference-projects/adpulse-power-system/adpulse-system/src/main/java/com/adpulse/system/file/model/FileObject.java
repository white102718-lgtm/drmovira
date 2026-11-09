package com.adpulse.system.file.model;

import com.adpulse.system.common.model.AuditedEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 去重后的物理文件对象。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class FileObject extends AuditedEntity {
    private String contentHash;
    private String hashAlgorithm;
    private Long fileSize;
    private String mimeType;
    private String storageProvider;
    private String bucketName;
    private String objectKey;
    private String storageStatus;
    private Long referenceCount;
}
