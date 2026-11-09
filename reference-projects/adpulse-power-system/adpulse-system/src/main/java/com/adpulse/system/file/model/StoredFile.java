package com.adpulse.system.file.model;

import com.adpulse.system.common.model.AuditedEntity;
import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Data;
import lombok.EqualsAndHashCode;

/** 用户可见的文件元数据记录。 */
@Data
@EqualsAndHashCode(callSuper = true)
public class StoredFile extends AuditedEntity {
    @JsonIgnore private Long fileObjectId;
    private String originalName;
    private String extension;
    private Long uploaderId;
    private String contentHash;
    private Long fileSize;
    private String mimeType;
    private String storageProvider;

    @JsonIgnore private String bucketName;

    @JsonIgnore private String objectKey;
}
