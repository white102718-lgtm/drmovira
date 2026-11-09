package com.adpulse.system.file.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

/** 文件接口请求对象。 */
public final class FileRequests {
    private FileRequests() {}

    /** 秒传预检请求。 */
    public record Precheck(
            @NotBlank @Size(max = 255) String fileName,
            @NotNull @Positive Long fileSize,
            @NotBlank String contentHash) {}
}
