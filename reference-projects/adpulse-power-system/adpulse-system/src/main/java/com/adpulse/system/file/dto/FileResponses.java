package com.adpulse.system.file.dto;

import com.adpulse.system.file.model.StoredFile;

/** 文件接口响应对象。 */
public final class FileResponses {
    private FileResponses() {}

    /** 预检结果；命中秒传时file为新建的当前用户文件记录。 */
    public record PrecheckResult(boolean instantUpload, StoredFile file) {}

    /** 下载所需的文件元数据和存储资源。 */
    public record DownloadFile(StoredFile file, org.springframework.core.io.Resource resource) {}
}
