package com.adpulse.main.adaccountasset;

import com.adpulse.main.adaccountasset.AdAccountAssetService.AdAccountAssetException;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportFailedFile;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportFailure;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportHistory;
import com.adpulse.main.adaccountasset.AdAccountAssetViews.ImportResult;
import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 广告账户文件导入、记录持久化与失败文件权限隔离服务。 */
@Service
public class AdAccountImportService {
    private final AdAccountAssetService assetService;
    private final AdAccountAssetMapper mapper;
    private final AdAccountImportCodec codec;
    private final IntegrationSecretCipher cipher;
    private final ObjectMapper objectMapper;

    public AdAccountImportService(
            AdAccountAssetService assetService,
            AdAccountAssetMapper mapper,
            AdAccountImportCodec codec,
            IntegrationSecretCipher cipher,
            ObjectMapper objectMapper) {
        this.assetService = assetService;
        this.mapper = mapper;
        this.codec = codec;
        this.cipher = cipher;
        this.objectMapper = objectMapper;
    }

    /** 解析上传文件、逐行导入并将失败工作簿加密保存。 */
    @Transactional
    public ImportResult importFile(byte[] content, String fileName) {
        AdAccountImportCodec.ParsedFile parsed = codec.read(content, fileName);
        ImportResult result =
                assetService.importAccounts(
                        parsed.rows().stream().map(AdAccountImportCodec.ParsedRow::item).toList());
        Map<Integer, AdAccountImportCodec.ParsedRow> rowsByLine =
                parsed.rows().stream()
                        .collect(
                                Collectors.toMap(
                                        AdAccountImportCodec.ParsedRow::line, Function.identity()));
        List<AdAccountImportCodec.RowFailure> failedRows =
                result.failures().stream()
                        .map(
                                failure -> {
                                    AdAccountImportCodec.ParsedRow row =
                                            rowsByLine.get(failure.line());
                                    if (row == null) {
                                        throw new AdAccountAssetException("导入失败行数据不完整");
                                    }
                                    return new AdAccountImportCodec.RowFailure(
                                            row, failure.message());
                                })
                        .toList();
        byte[] failedFile = codec.writeFailures(parsed, failedRows);
        saveImportLog(normalizeFileName(fileName), result, failedFile);
        return result;
    }

    /** 查询当前操作人的全部广告账户导入记录。 */
    public List<ImportHistory> history() {
        return mapper.findImportLogsByOperatorId(actorId()).stream().map(this::toHistory).toList();
    }

    /** 下载当前操作人自己的导入失败工作簿。 */
    public ImportFailedFile failedFile(Long id) {
        AdAccountImportLog log = mapper.findImportLogByIdAndOperatorId(id, actorId());
        if (log == null) throw new AdAccountAssetException("导入记录不存在");
        if (log.getFailedFileCiphertext() == null || log.getFailedFileCiphertext().isBlank()) {
            throw new AdAccountAssetException("该导入记录没有失败文件");
        }
        return new ImportFailedFile(
                cipher.decrypt(log.getFailedFileCiphertext()),
                stripExtension(log.getFileName()) + "导入失败数据.xlsx");
    }

    private void saveImportLog(String fileName, ImportResult result, byte[] failedFile) {
        AdAccountImportLog log = new AdAccountImportLog();
        log.setFileName(fileName);
        log.setTotalCount(result.totalCount());
        log.setSuccessCount(result.successCount());
        log.setFailureCount(result.failures().size());
        log.setFailureDetails(serializeFailures(result.failures()));
        log.setFailedFileCiphertext(
                failedFile.length == 0
                        ? null
                        : cipher.encrypt(Base64.getEncoder().encodeToString(failedFile)));
        log.setOperatorId(actorId());
        mapper.insertImportLog(log);
    }

    private ImportHistory toHistory(AdAccountImportLog log) {
        return new ImportHistory(
                String.valueOf(log.getId()),
                log.getFileName(),
                log.getTotalCount(),
                log.getSuccessCount(),
                deserializeFailures(log.getFailureDetails()),
                log.getCreatedAt());
    }

    private String serializeFailures(List<ImportFailure> failures) {
        try {
            return objectMapper.writeValueAsString(
                    failures.stream()
                            .map(failure -> new StoredFailure(failure.line(), failure.message()))
                            .toList());
        } catch (JsonProcessingException exception) {
            throw new AdAccountAssetException("导入记录序列化失败");
        }
    }

    private List<ImportFailure> deserializeFailures(String failureDetails) {
        try {
            List<StoredFailure> failures =
                    objectMapper.readValue(
                            failureDetails,
                            objectMapper
                                    .getTypeFactory()
                                    .constructCollectionType(List.class, StoredFailure.class));
            return failures.stream()
                    .map(failure -> new ImportFailure(failure.line(), null, failure.message()))
                    .toList();
        } catch (JsonProcessingException exception) {
            throw new AdAccountAssetException("导入记录数据损坏");
        }
    }

    private String normalizeFileName(String fileName) {
        if (fileName == null || fileName.isBlank()) return "未命名导入文件.xlsx";
        int separator = Math.max(fileName.lastIndexOf('/'), fileName.lastIndexOf('\\'));
        String baseName = fileName.substring(separator + 1).trim();
        if (baseName.isEmpty()) return "未命名导入文件.xlsx";
        return baseName.length() <= 255 ? baseName : baseName.substring(0, 255);
    }

    private String stripExtension(String fileName) {
        return fileName.replaceFirst("\\.[^.]+$", "");
    }

    private Long actorId() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null
                && authentication.getPrincipal() instanceof CurrentUser currentUser) {
            return currentUser.userId();
        }
        throw new AdAccountAssetException("登录状态无效");
    }

    /** 持久化失败摘要只保留行号与原因；原始账户字段仅存在于加密工作簿中。 */
    private record StoredFailure(int line, String message) {}
}
