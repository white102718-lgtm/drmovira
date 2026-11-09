package com.adpulse.system.asset.dto;

import java.time.LocalDateTime;
import java.util.List;

/** 资产 Excel 导入的服务端处理结果。 */
public final class AssetImportViews {
    private AssetImportViews() {}

    /** 导入汇总；失败文件由服务端生成后以 Base64 返回，浏览器只负责下载。 */
    public record Result(
            int totalCount,
            int successCount,
            List<Failure> failures,
            String failedFileBase64,
            String failedFileName) {}

    /** 当前用户可见的资产导入历史；失败明细不包含原始 Excel 数据。 */
    public record History(
            Long id,
            String assetSubtype,
            String fileName,
            int totalCount,
            int successCount,
            List<Failure> failures,
            LocalDateTime createdAt) {}

    /** 加密保存的失败工作簿仅在所属用户主动下载时返回。 */
    public record FailedFile(String contentBase64, String fileName) {}

    /** 单行失败信息。 */
    public record Failure(int line, String message) {}
}
