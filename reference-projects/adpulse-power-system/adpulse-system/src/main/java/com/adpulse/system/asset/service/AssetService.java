package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetImportViews;
import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.AssetMapper;
import com.adpulse.system.asset.model.ApprovalConfig;
import com.adpulse.system.asset.model.AssetApplication;
import com.adpulse.system.asset.model.AssetImportLog;
import com.adpulse.system.asset.model.ChannelReference;
import com.adpulse.system.asset.model.MediaAsset;
import com.adpulse.system.auth.service.MfaSecretCipher;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 统一资产库存、申请、审批和发放业务。 */
@Service
public class AssetService {
    private static final int IMPORT_HISTORY_MAX_PAGE_SIZE = 100;
    private static final ObjectMapper JSON_MAPPER = new ObjectMapper();
    private static final String AUDIT_SOURCE_MANUAL_EDIT = "MANUAL_EDIT";
    private static final String AUDIT_SOURCE_BATCH_EDIT = "BATCH_EDIT";
    private static final String AUDIT_SOURCE_EXCEL_BATCH = "EXCEL_BATCH";
    private static final String AUDIT_SOURCE_EXCEL_IMPORT = "EXCEL_IMPORT";
    private static final String AUDIT_SOURCE_MANUAL_CREATE = "MANUAL_CREATE";
    private static final String AUDIT_SOURCE_OPEN_ACCOUNT = "OPEN_ACCOUNT";
    private static final String AUDIT_SOURCE_SPREADSHEET_CREATE = "SPREADSHEET_CREATE";
    private static final Set<String> SENSITIVE_DETAIL_KEYS =
            Set.of("password", "cookie", "twoFa", "accessToken");
    private static final Map<String, String> AUDIT_DETAIL_LABELS =
            Map.ofEntries(
                    Map.entry("createDate", "创建日期"),
                    Map.entry("accountName", "账户名称"),
                    Map.entry("password", "密码"),
                    Map.entry("twoFa", "2FA"),
                    Map.entry("phoneNumber", "手机号"),
                    Map.entry("birthday", "生日"),
                    Map.entry("gender", "性别"),
                    Map.entry("assignmentDate", "分配日期"),
                    Map.entry("cookie", "Cookie"),
                    Map.entry("emailLoginUrl", "邮箱登录地址"),
                    Map.entry("date", "日期"),
                    Map.entry("usagePurpose", "使用用途"),
                    Map.entry("bmName", "BM 名称"),
                    Map.entry("bmId", "BM ID"),
                    Map.entry("bmLink", "BM 链接"),
                    Map.entry("operatorFbAccount", "操作 FB 账号"),
                    Map.entry("assignedDate", "分配日期"),
                    Map.entry("supplierRemoved", "供应商是否移除"),
                    Map.entry("pixelTestCode", "像素测试码"),
                    Map.entry("projectName", "项目名称"),
                    Map.entry("pixelName", "像素名称"),
                    Map.entry("accessToken", "Access Token"),
                    Map.entry("link", "链接"),
                    Map.entry("displayName", "显示名称"),
                    Map.entry("pageName", "主页名称"),
                    Map.entry("deviceName", "设备名称"),
                    Map.entry("brand", "品牌"),
                    Map.entry("model", "型号"),
                    Map.entry("serialNumber", "序列号"),
                    Map.entry("operatingSystem", "操作系统"),
                    Map.entry("purchaseDate", "购买日期"),
                    Map.entry("storageLocation", "存放位置"),
                    Map.entry("assetName", "资产名称"),
                    Map.entry("ipCountry", "IP 国家/地区"));
    private static final Pattern INVENTORY_SUBTYPE_PATTERN =
            Pattern.compile("\\\"inventorySubtype\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"");
    private static final Set<String> TYPES =
            Set.of(
                    "AD_ACCOUNT",
                    "PERSONAL",
                    "BM",
                    "PIXEL",
                    "TG",
                    "PAGE",
                    "COMPUTER",
                    "MOBILE",
                    "STATIC_IP",
                    "EMAIL");
    private static final Set<String> LEGACY_EMPTY_USAGE_USER_VALUES = Set.of("未分配", "未设置", "—");
    private static final Map<String, String> IDENTIFIER_DETAIL_KEYS =
            Map.ofEntries(
                    Map.entry("fb", "email"),
                    Map.entry("wechat", "wechatId"),
                    Map.entry("bm", "bmId"),
                    Map.entry("pixel", "pixelId"),
                    Map.entry("telegram", "phoneNumber"),
                    Map.entry("page", "pageName"),
                    Map.entry("computer", "assetCode"),
                    Map.entry("mobile", "deviceCode"),
                    Map.entry("static_ip", "ipAddress"),
                    Map.entry("email", "email"));
    private static final Map<String, String> NAME_DETAIL_KEYS =
            Map.ofEntries(
                    Map.entry("fb", "accountName"),
                    Map.entry("wechat", "displayName"),
                    Map.entry("bm", "bmName"),
                    Map.entry("pixel", "pixelName"),
                    Map.entry("page", "pageName"),
                    Map.entry("computer", "deviceName"),
                    Map.entry("mobile", "deviceName"),
                    Map.entry("static_ip", "assetName"),
                    Map.entry("email", "displayName"));
    private static final Map<String, Set<String>> BATCH_EDITABLE_DETAIL_KEYS =
            Map.ofEntries(
                    Map.entry(
                            "fb",
                            Set.of(
                                    "createDate",
                                    "accountName",
                                    "password",
                                    "twoFa",
                                    "phoneNumber",
                                    "birthday",
                                    "gender",
                                    "assignmentDate",
                                    "cookie",
                                    "emailLoginUrl")),
                    Map.entry(
                            "bm",
                            Set.of(
                                    "date",
                                    "usagePurpose",
                                    "bmName",
                                    "bmLink",
                                    "operatorFbAccount",
                                    "assignedDate",
                                    "supplierRemoved")),
                    Map.entry(
                            "pixel",
                            Set.of(
                                    "pixelTestCode",
                                    "bmName",
                                    "bmId",
                                    "projectName",
                                    "pixelName",
                                    "accessToken")),
                    Map.entry("telegram", Set.of("link")),
                    Map.entry("wechat", Set.of("displayName", "phoneNumber")),
                    Map.entry("page", Set.of("pageName")),
                    Map.entry(
                            "computer",
                            Set.of(
                                    "deviceName",
                                    "brand",
                                    "model",
                                    "serialNumber",
                                    "operatingSystem",
                                    "purchaseDate",
                                    "storageLocation")),
                    Map.entry(
                            "mobile",
                            Set.of(
                                    "deviceName",
                                    "brand",
                                    "model",
                                    "phoneNumber",
                                    "operatingSystem",
                                    "purchaseDate")),
                    Map.entry("static_ip", Set.of("assetName", "ipCountry")),
                    Map.entry(
                            "email", Set.of("displayName", "password", "twoFa", "emailLoginUrl")));
    private static final Map<String, Set<String>> REQUIRED_BATCH_DETAIL_KEYS =
            Map.ofEntries(
                    Map.entry("fb", Set.of("createDate", "password", "twoFa")),
                    Map.entry("pixel", Set.of("bmName", "bmId", "pixelName")),
                    Map.entry("telegram", Set.of("link")),
                    Map.entry("email", Set.of("password")));
    private final AssetMapper mapper;
    private final AssetExcelCodec excelCodec;
    private final MfaSecretCipher secretCipher;
    private final AssetLifecycleService lifecycleService;

    public AssetService(
            AssetMapper mapper, AssetExcelCodec excelCodec, MfaSecretCipher secretCipher) {
        this(mapper, excelCodec, secretCipher, null);
    }

    @Autowired
    public AssetService(
            AssetMapper mapper,
            AssetExcelCodec excelCodec,
            MfaSecretCipher secretCipher,
            AssetLifecycleService lifecycleService) {
        this.mapper = mapper;
        this.excelCodec = excelCodec;
        this.secretCipher = secretCipher;
        this.lifecycleService = lifecycleService;
    }

    /** 查询全部资产库存。 */
    public List<MediaAsset> assets(String assetType, String channelId) {
        return reveal(mapper.findAssets(typeOrNull(assetType), null, textOrNull(channelId)));
    }

    /** 查询当前用户获批资产。 */
    public List<MediaAsset> myAssets() {
        return reveal(mapper.findAssets(null, SecurityContextHelper.currentUserId(), null));
    }

    /**
     * 按资产管理页的可见字段完成服务端筛选和分页。
     *
     * <p>明细字段存放在加密 JSON 中，无法直接复用数据库列筛选；因此先在服务端解密、匹配后再仅返回当前页， 避免将完整库存传递给浏览器。
     */
    public AssetViews.AssetPage searchAssets(AssetRequests.AssetSearch request) {
        int page = request.page() == null ? 1 : request.page();
        int pageSize = request.pageSize() == null ? 20 : request.pageSize();
        List<MediaAsset> matched = searchAllAssets(request);
        int from = Math.min((page - 1) * pageSize, matched.size());
        int to = Math.min(from + pageSize, matched.size());
        return new AssetViews.AssetPage(matched.subList(from, to), matched.size(), page, pageSize);
    }

    /** 按列表相同口径返回全部筛选结果，避免导出端逐页重复查询和解密。 */
    public List<MediaAsset> searchAllAssets(AssetRequests.AssetSearch request) {
        return reveal(
                        mapper.findAssets(
                                typeOrNull(request.assetType()),
                                request.mine() ? SecurityContextHelper.currentUserId() : null,
                                null))
                .stream()
                .filter(asset -> matchesSearch(asset, request))
                .toList();
    }

    private boolean matchesSearch(MediaAsset asset, AssetRequests.AssetSearch request) {
        Map<String, String> details = assetDetails(asset.getSecretData());
        if (!matchesText(resolveSubtype(asset, details), request.subtype())) return false;
        if (!matchesKeyword(asset, details, request.keyword())) return false;

        Map<String, List<String>> filters = searchFilterValues(request);
        Map<String, String> controls =
                request.filterControls() == null ? Map.of() : request.filterControls();
        return filters.entrySet().stream()
                .allMatch(
                        entry ->
                                matchesFilter(
                                        filterValue(asset, details, entry.getKey()),
                                        entry.getValue(),
                                        controls.get(entry.getKey())));
    }

    /** 新版多值筛选优先；旧版单值参数仍按单元素列表处理，保证接口灰度升级兼容。 */
    private Map<String, List<String>> searchFilterValues(AssetRequests.AssetSearch request) {
        Map<String, List<String>> values = new LinkedHashMap<>();
        if (request.filters() != null) {
            request.filters()
                    .forEach(
                            (key, value) -> {
                                String normalized = textOrNull(value);
                                if (normalized != null) values.put(key, List.of(normalized));
                            });
        }
        if (request.filterValues() != null) {
            request.filterValues()
                    .forEach(
                            (key, candidates) -> {
                                List<String> normalized =
                                        candidates.stream()
                                                .map(this::textOrNull)
                                                .filter(Objects::nonNull)
                                                .distinct()
                                                .toList();
                                if (normalized.isEmpty()) values.remove(key);
                                else values.put(key, normalized);
                            });
        }
        return values;
    }

    private Map<String, String> assetDetails(String secretData) {
        if (secretData == null || secretData.isBlank()) return Map.of();
        try {
            Map<String, Object> values =
                    JSON_MAPPER.readValue(secretData, new TypeReference<Map<String, Object>>() {});
            Map<String, String> details = new LinkedHashMap<>();
            values.forEach((key, value) -> details.put(key, Objects.toString(value, "")));
            return details;
        } catch (JsonProcessingException exception) {
            return Map.of();
        }
    }

    private String resolveSubtype(MediaAsset asset, Map<String, String> details) {
        String subtype = textOrNull(details.get("inventorySubtype"));
        if (subtype != null) return subtype;
        return switch (asset.getAssetType()) {
            case "AD_ACCOUNT" -> "ad_account";
            case "PERSONAL" -> "fb";
            case "STATIC_IP" -> "static_ip";
            case "TG" -> "telegram";
            default -> asset.getAssetType().toLowerCase(Locale.ROOT);
        };
    }

    private boolean matchesKeyword(MediaAsset asset, Map<String, String> details, String keyword) {
        String expected = normalizedText(keyword);
        if (expected.isEmpty()) return true;

        List<String> values = new ArrayList<>(details.values());
        values.add(textValue(asset.getId()));
        values.add(asset.getAssetType());
        values.add(asset.getAssetName());
        values.add(asset.getAssetCode());
        values.add(asset.getProjectId());
        values.add(asset.getProjectName());
        values.add(asset.getChannelId());
        values.add(asset.getChannelName());
        values.add(asset.getStatus());
        values.add(textValue(asset.getAssigneeId()));
        values.add(asset.getAssigneeName());
        values.add(asset.getAssigneeDepartmentName());
        values.add(asset.getUsageUserIds());
        values.add(asset.getUsageUserNames());
        values.add(asset.getUsageDepartmentNames());
        values.add(textValue(asset.getApplicationId()));
        values.add(asset.getRemark());
        return values.stream().anyMatch(value -> normalizedText(value).contains(expected));
    }

    private boolean matchesFilter(String actual, List<String> expectedValues, String control) {
        String normalizedActual = normalizedText(actual);
        return expectedValues.stream()
                .map(this::normalizedText)
                .filter(expected -> !expected.isEmpty())
                .anyMatch(
                        expected -> {
                            if ("select".equals(control)) return expected.equals(normalizedActual);
                            if ("date".equals(control))
                                return normalizedActual.startsWith(expected);
                            return normalizedActual.contains(expected);
                        });
    }

    private boolean matchesText(String actual, String expected) {
        String normalizedExpected = normalizedText(expected);
        return normalizedExpected.isEmpty() || normalizedText(actual).contains(normalizedExpected);
    }

    private String filterValue(MediaAsset asset, Map<String, String> details, String key) {
        if (key.startsWith("details.")) return details.get(key.substring("details.".length()));
        return switch (key) {
            case "applicationId" -> textValue(asset.getApplicationId());
            case "assigneeId" -> textValue(asset.getAssigneeId());
            case "assigneeIds" -> asset.getUsageUserIds();
            case "channelId" -> asset.getChannelId();
            case "channelName" -> asset.getChannelName();
            case "createdAt" -> textValue(asset.getCreatedAt());
            case "id" -> textValue(asset.getId());
            case "identifier" -> asset.getAssetCode();
            case "name" -> asset.getAssetName();
            case "note" -> asset.getRemark();
            case "owner" -> firstNonBlank(asset.getUsageUserNames(), asset.getAssigneeName());
            case "projectId" -> asset.getProjectId();
            case "projectName" -> asset.getProjectName();
            case "status" -> frontendStatus(asset.getStatus());
            case "usageDepartment" ->
                    joinNonBlank(
                            asset.getUsageTeam(),
                            asset.getUsageDepartmentNames(),
                            asset.getAssigneeDepartmentName());
            default -> "";
        };
    }

    private String frontendStatus(String status) {
        return switch (status) {
            case "ASSIGNED" -> "allocated";
            case "AVAILABLE" -> "available";
            case "RETURN_PENDING" -> "return_pending";
            default -> "exception";
        };
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            String normalized = textOrNull(value);
            if (normalized != null) return normalized;
        }
        return "";
    }

    private String joinNonBlank(String... values) {
        return Arrays.stream(values)
                .map(this::textOrNull)
                .filter(Objects::nonNull)
                .distinct()
                .reduce((left, right) -> left + " " + right)
                .orElse("");
    }

    private String textValue(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private String normalizedText(String value) {
        String normalized = textOrNull(value);
        return normalized == null ? "" : normalized.toLowerCase(Locale.ROOT);
    }

    /**
     * 处理人员离职时的资产归属。
     *
     * <p>直接分配的资产会恢复可分配；像素和广告账户是可共享资产，因此仅解除离职人员的有效关系，其他使用人不受影响。
     */
    public void releaseAssetsForDepartingUser(Long userId, Long operatorId) {
        long deletedAt = System.currentTimeMillis();
        mapper.refreshChannelAccountUsageForDepartingUser(userId, operatorId);
        mapper.deactivateChannelAccountAssignmentsForUser(userId, deletedAt, operatorId);
        mapper.releaseUnassignedAdAccountAssets(operatorId);
        mapper.deactivatePixelUsageAssignmentsForUser(userId, deletedAt, operatorId);
        mapper.releaseAssetsAssignedToUser(userId, operatorId);
    }

    /** 项目结项办理完成后释放该项目占用的全部像素，并清除已废弃的使用人关联。 */
    @Transactional
    public int releasePixelsForProject(String projectId, Long operatorId) {
        String normalizedProjectId = textOrNull(projectId);
        if (normalizedProjectId == null) throw BusinessException.validation("结项申请缺少项目");
        List<MediaAsset> assignedPixels = mapper.findAssignedPixelsByProject(normalizedProjectId);
        mapper.deactivatePixelUsageAssignmentsForProject(
                normalizedProjectId, System.currentTimeMillis(), operatorId);
        int released = mapper.releasePixelsForProject(normalizedProjectId, operatorId);
        for (MediaAsset pixel : assignedPixels) {
            pixel.setStatus("AVAILABLE");
            pixel.setApplicationId(null);
            pixel.setAssigneeId(null);
            pixel.setAssigneeName(null);
            recordLifecycle("RELEASED", pixel, "项目结项释放像素");
        }
        return released;
    }

    /** 校验加密库存详情中的前端子类型；Facebook 个号统一使用 fb。 */
    public boolean matchesInventorySubtype(String encryptedSecretData, String expectedSubtype) {
        if (expectedSubtype == null || expectedSubtype.isBlank()) return true;
        String actualSubtype = "fb";
        if (encryptedSecretData != null && !encryptedSecretData.isBlank()) {
            String secretData = secretCipher.decrypt(encryptedSecretData);
            Matcher matcher = INVENTORY_SUBTYPE_PATTERN.matcher(secretData);
            if (matcher.find()) actualSubtype = matcher.group(1).trim();
        }
        return expectedSubtype.trim().equalsIgnoreCase(actualSubtype);
    }

    /**
     * 从申请表快照解析办理阶段实际需要的库存类型。
     *
     * @param applicationType 审批配置类型
     * @param applicationData 申请表快照
     * @param assignment 办理节点资源分配配置
     * @return 库存主类型与可选子类型
     */
    public InventorySelection resolveInventorySelection(
            String applicationType,
            Map<String, Object> applicationData,
            Map<String, Object> assignment) {
        String fieldKey = Objects.toString(assignment.get("assetTypeFieldKey"), "").trim();
        if (fieldKey.isBlank() && applicationData.containsKey("socialAssetType")) {
            fieldKey = "socialAssetType";
        }
        if (fieldKey.isBlank()) return new InventorySelection(applicationType, "");

        String requestedType = Objects.toString(applicationData.get(fieldKey), "").trim();
        if (requestedType.isBlank()) throw BusinessException.validation("申请缺少社交资产类型");
        String normalized = requestedType.toLowerCase(Locale.ROOT).replace(" ", "");
        if (Set.of("tg", "tg号", "telegram").contains(normalized)) {
            return new InventorySelection("TG", "");
        }
        if (Set.of("微信", "微信号", "wechat").contains(normalized)) {
            return new InventorySelection("PERSONAL", "wechat");
        }
        if (Set.of("facebook", "facebook账号", "facebookaccount", "个号").contains(normalized)) {
            return new InventorySelection("PERSONAL", "fb");
        }
        String inventoryType = requestedType.toUpperCase(Locale.ROOT);
        if (!TYPES.contains(inventoryType)) throw BusinessException.validation("不支持的社交资产类型");
        return new InventorySelection(inventoryType, "");
    }

    /** 办理阶段使用的库存主类型与 PERSONAL 子类型。 */
    public record InventorySelection(String assetType, String subtype) {}

    /** 新增资产。 */
    @Transactional
    public MediaAsset createAsset(AssetRequests.AssetSave request) {
        return createAsset(request, AUDIT_SOURCE_MANUAL_CREATE);
    }

    private MediaAsset createAsset(AssetRequests.AssetSave request, String stockedSource) {
        List<Long> sharedUsageUserIds = resolveSharedUsageUserIds(request);
        MediaAsset asset = apply(new MediaAsset(), request, sharedUsageUserIds);
        Long userId = SecurityContextHelper.currentUserId();
        asset.setCreatedBy(userId);
        asset.setUpdatedBy(userId);
        try {
            mapper.insertAsset(asset);
        } catch (DuplicateKeyException exception) {
            throw BusinessException.conflict("资产标识已存在");
        }
        syncSharedUsageUsers(asset, sharedUsageUserIds, userId);
        MediaAsset created = reveal(mapper.findAsset(asset.getId()));
        recordStocked(created, stockedSource);
        if ("ASSIGNED".equals(created.getStatus())) {
            recordLifecycle("ASSIGNED", created, "入库时已分配使用人");
        }
        return created;
    }

    /**
     * 服务端统一解析并写入资产 Excel。
     *
     * <p>单行异常不会回滚已经成功的行；失败行由服务端直接生成带失败原因的工作簿，前端无需读取或校验 Excel 内容。
     */
    @Transactional
    public AssetImportViews.Result importAssets(byte[] content, String subtype) {
        return importAssets(content, subtype, "未命名导入文件.xlsx");
    }

    /**
     * 服务端统一解析并写入资产 Excel，同时写入仅操作人可查询的导入记录。
     *
     * <p>失败工作簿可能包含密码或 2FA 等敏感列，数据库中只能保存 AES-GCM 密文。
     */
    @Transactional
    public AssetImportViews.Result importAssets(byte[] content, String subtype, String fileName) {
        AssetExcelCodec.ParsedWorkbook workbook = excelCodec.read(content, subtype, fileName);
        List<AssetExcelCodec.RowFailure> failures = new ArrayList<>();
        Long operatorId = SecurityContextHelper.currentUserId();
        Set<String> importedIdentifiers = new HashSet<>();
        int successCount = 0;
        for (AssetExcelCodec.ParsedRow row : workbook.rows()) {
            try {
                importRow(workbook.spec(), row, operatorId, importedIdentifiers);
                successCount++;
            } catch (BusinessException exception) {
                failures.add(new AssetExcelCodec.RowFailure(row, exception.getMessage()));
            } catch (DuplicateKeyException exception) {
                failures.add(new AssetExcelCodec.RowFailure(row, "资产保存冲突，请重新导入"));
            }
        }
        byte[] failedFile =
                failures.isEmpty() ? new byte[0] : excelCodec.writeFailures(workbook, failures);
        List<AssetImportViews.Failure> resultFailures =
                failures.stream()
                        .map(
                                failure ->
                                        new AssetImportViews.Failure(
                                                failure.row().line(), failure.message()))
                        .toList();
        String failedFileName =
                failures.isEmpty() ? null : workbook.spec().sheetName() + "导入失败数据.xlsx";
        String failedFileBase64 =
                failedFile.length == 0 ? null : Base64.getEncoder().encodeToString(failedFile);
        AssetImportViews.Result result =
                new AssetImportViews.Result(
                        workbook.rows().size(),
                        successCount,
                        resultFailures,
                        failedFileBase64,
                        failedFileName);
        saveImportLog(workbook.spec().subtype(), fileName, operatorId, result);
        return result;
    }

    /** 分页查询当前用户自己创建的资产导入记录，不提供跨用户查询入口。 */
    public PageResult<AssetImportViews.History> importHistory(int page, int pageSize) {
        int safePage = Math.max(page, 1);
        int safePageSize = Math.min(Math.max(pageSize, 1), IMPORT_HISTORY_MAX_PAGE_SIZE);
        Long operatorId = SecurityContextHelper.currentUserId();
        return new PageResult<>(
                mapper.findImportLogsByOperatorId(
                                operatorId, (safePage - 1L) * safePageSize, safePageSize)
                        .stream()
                        .map(this::toImportHistory)
                        .toList(),
                mapper.countImportLogsByOperatorId(operatorId),
                safePage,
                safePageSize);
    }

    /** 下载当前用户自己导入时生成的失败工作簿。 */
    public AssetImportViews.FailedFile failedImportFile(Long id) {
        AssetImportLog importLog =
                mapper.findImportLogByIdAndOperatorId(id, SecurityContextHelper.currentUserId());
        if (importLog == null) throw BusinessException.notFound("导入记录");
        if (importLog.getFailedFileCiphertext() == null
                || importLog.getFailedFileCiphertext().isBlank()) {
            throw BusinessException.validation("该导入记录没有失败文件");
        }
        return new AssetImportViews.FailedFile(
                secretCipher.decrypt(importLog.getFailedFileCiphertext()),
                importLog.getFileName().replaceFirst("\\.[^.]+$", "") + "导入失败数据.xlsx");
    }

    private void saveImportLog(
            String assetSubtype,
            String fileName,
            Long operatorId,
            AssetImportViews.Result importResult) {
        AssetImportLog importLog = new AssetImportLog();
        importLog.setAssetSubtype(assetSubtype);
        importLog.setFileName(normalizeImportFileName(fileName));
        importLog.setTotalCount(importResult.totalCount());
        importLog.setSuccessCount(importResult.successCount());
        importLog.setFailureCount(importResult.failures().size());
        importLog.setFailureDetails(serializeFailures(importResult.failures()));
        importLog.setFailedFileCiphertext(
                importResult.failedFileBase64() == null
                        ? null
                        : secretCipher.encrypt(importResult.failedFileBase64()));
        importLog.setOperatorId(operatorId);
        mapper.insertImportLog(importLog);
    }

    private AssetImportViews.History toImportHistory(AssetImportLog importLog) {
        return new AssetImportViews.History(
                importLog.getId(),
                importLog.getAssetSubtype(),
                importLog.getFileName(),
                importLog.getTotalCount(),
                importLog.getSuccessCount(),
                deserializeFailures(importLog.getFailureDetails()),
                importLog.getCreatedAt());
    }

    private String serializeFailures(List<AssetImportViews.Failure> failures) {
        try {
            return JSON_MAPPER.writeValueAsString(failures);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("导入记录序列化失败");
        }
    }

    private List<AssetImportViews.Failure> deserializeFailures(String failureDetails) {
        try {
            return JSON_MAPPER.readValue(
                    failureDetails,
                    JSON_MAPPER
                            .getTypeFactory()
                            .constructCollectionType(List.class, AssetImportViews.Failure.class));
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("导入记录数据损坏");
        }
    }

    private String normalizeImportFileName(String fileName) {
        String normalizedName = textOrNull(fileName);
        if (normalizedName == null) return "未命名导入文件.xlsx";
        int separatorIndex =
                Math.max(normalizedName.lastIndexOf('/'), normalizedName.lastIndexOf('\\'));
        String baseName = normalizedName.substring(separatorIndex + 1);
        if (baseName.isBlank()) return "未命名导入文件.xlsx";
        return baseName.length() <= 255 ? baseName : baseName.substring(0, 255);
    }

    private void importRow(
            AssetExcelCodec.ImportSpec spec,
            AssetExcelCodec.ParsedRow row,
            Long operatorId,
            Set<String> importedIdentifiers) {
        Map<String, String> values = row.values();
        for (String requiredHeader : spec.requiredHeaders()) {
            if (textOrNull(values.get(requiredHeader)) == null) {
                throw BusinessException.validation(
                        requiredHeader.replaceFirst("^\\*", "") + "不能为空");
            }
        }
        String assetName = textOrNull(values.get(spec.nameHeader()));
        String assetCode = importAssetCode(spec, assetName, values);
        if (assetCode == null) throw BusinessException.validation("资产唯一标识不能为空");
        String duplicateKey = spec.assetType() + "\u0000" + assetCode;
        if (!importedIdentifiers.add(duplicateKey)) {
            throw BusinessException.validation("同一文件中存在重复的资产唯一标识");
        }

        MediaAsset asset = findImportedAsset(spec, assetCode, assetName);
        boolean existing = asset != null;
        AssetAuditSnapshot before = existing ? auditSnapshot(asset) : null;
        if (existing && "RETURN_PENDING".equals(asset.getStatus())) {
            throw BusinessException.conflict("回收中的资产不能修改");
        }
        if (asset == null) asset = new MediaAsset();
        List<Long> usageUserIds =
                applyImportedAsset(asset, spec, values, assetName, assetCode, operatorId);
        if (existing) {
            mapper.updateAsset(asset);
        } else {
            try {
                mapper.insertAsset(asset);
            } catch (DuplicateKeyException exception) {
                // 并发导入同一标识时，唯一约束负责仲裁；随后按同一行数据更新已落库记录。
                MediaAsset concurrentAsset = findImportedAsset(spec, assetCode, assetName);
                if (concurrentAsset == null) throw exception;
                if ("RETURN_PENDING".equals(concurrentAsset.getStatus())) {
                    throw BusinessException.conflict("回收中的资产不能修改");
                }
                before = auditSnapshot(concurrentAsset);
                existing = true;
                usageUserIds =
                        applyImportedAsset(
                                concurrentAsset, spec, values, assetName, assetCode, operatorId);
                mapper.updateAsset(concurrentAsset);
                asset = concurrentAsset;
            }
        }
        syncSharedUsageUsers(asset, usageUserIds, operatorId);
        MediaAsset persisted = mapper.findAsset(asset.getId());
        if (existing) {
            recordUpdate(before, auditSnapshot(persisted), persisted, AUDIT_SOURCE_EXCEL_IMPORT);
        } else {
            recordStocked(reveal(persisted), AUDIT_SOURCE_EXCEL_IMPORT);
        }
    }

    /** 主页从本次导入起以主页名称作为库存唯一标识，主页 ID 仅保存在加密详情中。 */
    private String importAssetCode(
            AssetExcelCodec.ImportSpec spec, String assetName, Map<String, String> values) {
        if ("PAGE".equals(spec.assetType())) return assetName;
        return textOrNull(values.get(spec.identifierHeader()));
    }

    private MediaAsset findImportedAsset(
            AssetExcelCodec.ImportSpec spec, String assetCode, String assetName) {
        MediaAsset matchedByCode = mapper.findAssetByTypeAndCode(spec.assetType(), assetCode);
        if (matchedByCode != null || !"PAGE".equals(spec.assetType())) return matchedByCode;

        // 历史主页可能仍以主页 ID 为编码；重新导入时只在名称唯一时原地升级，避免批量迁移。
        List<MediaAsset> matchedByName = mapper.findAssetsByTypeAndName("PAGE", assetName);
        if (matchedByName.size() > 1) {
            throw BusinessException.conflict("主页名称对应多条历史资产，请先清理重复数据");
        }
        return matchedByName.isEmpty() ? null : matchedByName.getFirst();
    }

    private List<Long> applyImportedAsset(
            MediaAsset asset,
            AssetExcelCodec.ImportSpec spec,
            Map<String, String> values,
            String assetName,
            String assetCode,
            Long operatorId) {
        asset.setAssetType(spec.assetType());
        asset.setAssetCode(assetCode);
        asset.setAssetName(assetName == null ? assetCode : assetName);
        if ("PIXEL".equals(spec.assetType())) {
            applyPixelImportAssignment(asset, values.get("所属项目"), values.get("使用团队"));
        } else {
            asset.setUsageTeam(null);
            ChannelReference channel = resolveImportChannel(spec, values.get("渠道名称"));
            asset.setChannelId(channel == null ? null : String.valueOf(channel.id()));
            asset.setChannelName(channel == null ? null : channel.channelName());
            // 导入资产的渠道归属必须与渠道管理中的正常渠道一致，避免写入无法筛选和分配的名称快照。
            asset.setProjectId(asset.getChannelId());
            asset.setProjectName(asset.getChannelName());
        }
        asset.setSecretData(secretCipher.encrypt(serializeImportDetails(spec, values)));
        asset.setRemark(textOrNull(values.get("备注")));
        if (asset.getId() == null) asset.setCreatedBy(operatorId);
        asset.setUpdatedBy(operatorId);
        return "PIXEL".equals(spec.assetType())
                ? List.of()
                : applyExcelAssignment(asset, values.get("使用人"));
    }

    /** 像素导入允许同时建立项目和使用团队归属；两个字段必须同时填写或同时留空。 */
    private void applyPixelImportAssignment(
            MediaAsset asset, String projectName, String usageTeam) {
        String normalizedProjectName = textOrNull(projectName);
        String normalizedUsageTeam = textOrNull(usageTeam);
        asset.setChannelId(null);
        asset.setChannelName(null);
        asset.setAssigneeId(null);
        asset.setAssigneeName(null);
        asset.setApplicationId(null);
        if (normalizedProjectName == null && normalizedUsageTeam == null) {
            asset.setProjectId(null);
            asset.setProjectName(null);
            asset.setUsageTeam(null);
            asset.setStatus("AVAILABLE");
            return;
        }
        if (normalizedProjectName == null || normalizedUsageTeam == null) {
            throw BusinessException.validation("所属项目和使用团队必须同时填写");
        }

        List<Long> projectIds = mapper.findActiveProjectIdsByName(normalizedProjectName);
        if (projectIds.isEmpty()) throw BusinessException.validation("所属项目不存在");
        if (projectIds.size() > 1) {
            throw BusinessException.validation("所属项目重名，请填写系统内唯一名称");
        }
        requireUniqueActiveDepartment(normalizedUsageTeam);
        asset.setProjectId(String.valueOf(projectIds.getFirst()));
        asset.setProjectName(normalizedProjectName);
        asset.setUsageTeam(normalizedUsageTeam);
        asset.setStatus("ASSIGNED");
    }

    private List<Long> applyExcelAssignment(MediaAsset asset, String usageUser) {
        String normalizedUser = textOrNull(usageUser);
        // 历史导出文件曾把空使用人写成页面占位符；这里只兼容该结构化字段，避免误清空自由文本。
        if (normalizedUser != null && LEGACY_EMPTY_USAGE_USER_VALUES.contains(normalizedUser)) {
            normalizedUser = null;
        }
        if (normalizedUser == null) {
            applyManualAssignment(asset, "AVAILABLE", null);
            return List.of();
        }
        List<Long> userIds = new ArrayList<>();
        for (String userName : normalizedUser.split("[,，、;；\\n\\r]+")) {
            String normalizedName = textOrNull(userName);
            if (normalizedName == null) continue;
            List<Long> matchedUserIds = mapper.findActiveUserIdsByName(normalizedName);
            if (matchedUserIds.isEmpty()) throw BusinessException.validation("使用人不存在或已停用");
            if (matchedUserIds.size() > 1) throw BusinessException.validation("使用人重名，请填写系统内唯一名称");
            if (!userIds.contains(matchedUserIds.getFirst()))
                userIds.add(matchedUserIds.getFirst());
        }
        if (userIds.isEmpty()) throw BusinessException.validation("使用人不存在或已停用");
        applyManualAssignment(asset, "ASSIGNED", userIds.getFirst());
        return userIds;
    }

    private String serializeImportDetails(
            AssetExcelCodec.ImportSpec spec, Map<String, String> values) {
        Map<String, String> details = new LinkedHashMap<>();
        details.put("inventorySubtype", spec.subtype());
        for (Map.Entry<String, String> entry : values.entrySet()) {
            if ("PIXEL".equals(spec.assetType())
                    && Set.of("所属项目", "使用团队").contains(entry.getKey())) {
                continue;
            }
            String key = excelDetailKey(entry.getKey());
            String value = normalizeExcelDetailValue(entry.getKey(), entry.getValue());
            if (key != null && !value.isBlank()) details.put(key, value);
        }
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(details);
        } catch (com.fasterxml.jackson.core.JsonProcessingException exception) {
            throw BusinessException.conflict("资产导入数据转换失败");
        }
    }

    /**
     * 导入模板中带有渠道名称列的资产必须关联渠道管理中的唯一正常渠道。
     *
     * <p>渠道名称是用户可编辑的展示字段，不能作为稳定关联键；名称重复时拒绝整行， 防止把资产随机归属到同名渠道。
     */
    private ChannelReference resolveImportChannel(
            AssetExcelCodec.ImportSpec spec, String channelName) {
        if (!spec.headers().contains("渠道名称")) return null;
        String normalizedName = textOrNull(channelName);
        if (normalizedName == null) throw BusinessException.validation("渠道名称不能为空");

        List<ChannelReference> channels = mapper.findActiveChannelsByName(normalizedName);
        if (channels.isEmpty()) throw BusinessException.validation("渠道不存在或已停用");
        if (channels.size() > 1) {
            throw BusinessException.validation("渠道名称重复，请填写唯一的渠道名称");
        }
        return channels.getFirst();
    }

    /** 保留手工录入的历史兼容行为：只有唯一命中的正常渠道才建立 ID 关联。 */
    private ChannelReference resolveManualChannel(String channelName) {
        String normalizedName = textOrNull(channelName);
        if (normalizedName == null) return null;

        List<ChannelReference> channels = mapper.findActiveChannelsByName(normalizedName);
        return channels.size() == 1
                ? channels.getFirst()
                : new ChannelReference(null, normalizedName);
    }

    /** Excel 模板展示中文选项，但库存详情持久化稳定枚举值，兼容旧模板中已有的枚举编码。 */
    private String normalizeExcelDetailValue(String header, String value) {
        String normalizedValue = textOrNull(value);
        if (normalizedValue == null) return "";

        return switch (header) {
            case "性别" ->
                    switch (normalizedValue.toUpperCase(Locale.ROOT)) {
                        case "男", "MALE" -> "MALE";
                        case "女", "FEMALE" -> "FEMALE";
                        default -> throw BusinessException.validation("性别仅支持“男”或“女”");
                    };
            case "是否移除供应商" ->
                    switch (normalizedValue.toUpperCase(Locale.ROOT)) {
                        case "是", "YES" -> "YES";
                        case "否", "NO" -> "NO";
                        default -> throw BusinessException.validation("是否移除供应商仅支持“是”或“否”");
                    };
            default -> normalizedValue;
        };
    }

    private String excelDetailKey(String header) {
        return switch (header) {
            case "*个号创建日期" -> "createDate";
            case "名字" -> "accountName";
            case "*邮箱", "*邮箱账号" -> "email";
            case "*密码", "*邮箱密码" -> "password";
            case "*2fa", "2FA 密钥" -> "twoFa";
            case "手机号", "绑定手机号" -> "phoneNumber";
            case "生日" -> "birthday";
            case "性别" -> "gender";
            case "分配日期" -> "assignmentDate";
            case "Cookie" -> "cookie";
            case "邮箱登录网址" -> "emailLoginUrl";
            case "日期" -> "date";
            case "使用途径" -> "usagePurpose";
            case "BM 名称", "*BM名称" -> "bmName";
            case "*BMID", "*创建BMID" -> "bmId";
            case "BM 链接" -> "bmLink";
            case "使用人个号" -> "operatorFbAccount";
            case "BM 挂日期" -> "assignedDate";
            case "是否移除供应商" -> "supplierRemoved";
            case "*像素名称" -> "pixelName";
            case "*像素ID" -> "pixelId";
            case "Access Token" -> "accessToken";
            case "像素测试代码" -> "pixelTestCode";
            case "团队名称" -> "teamName";
            case "*电话号码" -> "phoneNumber";
            case "*TG 链接" -> "link";
            case "*微信号" -> "wechatId";
            case "微信昵称" -> "displayName";
            case "主页 ID", "*主页 ID" -> "pageId";
            case "主页名称", "*主页名称" -> "pageName";
            case "*资产编号" -> "assetCode";
            case "电脑名称", "手机名称" -> "deviceName";
            case "品牌" -> "brand";
            case "型号" -> "model";
            case "序列号" -> "serialNumber";
            case "操作系统" -> "operatingSystem";
            case "购买日期" -> "purchaseDate";
            case "存放位置" -> "storageLocation";
            case "*IMEI / 序列号" -> "deviceCode";
            case "IP名称" -> "assetName";
            case "*IP 地址" -> "ipAddress";
            case "IP 国家" -> "ipCountry";
            case "使用团队" -> "usageTeam";
            case "邮箱名称" -> "displayName";
            default -> null;
        };
    }

    /**
     * 将广告户申请办理时选中的渠道账户登记到资产主表。
     *
     * <p>广告账户主记录按账户 ID 唯一；多人申请关系由 {@code media_channel_account_assignment}
     * 留存。因此遇到既有主记录时复用它，不能阻断后续申请。
     */
    @Transactional
    public List<MediaAsset> registerOpenedAdAccounts(
            String rawAccountIds,
            String requestedName,
            String channelId,
            String channelName,
            long applicationId,
            long assigneeId,
            String assigneeName,
            long operatorId) {
        List<String> accountIds =
                Arrays.stream(Objects.toString(rawAccountIds, "").split("[;\\n\\r]+"))
                        .map(String::trim)
                        .filter(item -> !item.isBlank())
                        .distinct()
                        .toList();
        if (accountIds.isEmpty()) {
            throw BusinessException.validation("请至少选择一个已开户广告账户");
        }

        String normalizedName = Objects.toString(requestedName, "").trim();
        List<MediaAsset> registered = new ArrayList<>();
        for (String accountId : accountIds) {
            MediaAsset asset = new MediaAsset();
            asset.setAssetType("AD_ACCOUNT");
            asset.setAssetCode(accountId);
            asset.setAssetName(
                    accountIds.size() == 1 && !normalizedName.isBlank()
                            ? normalizedName
                            : "广告账户 " + accountId);
            asset.setProjectId(textOrNull(channelId));
            asset.setProjectName(textOrNull(channelName));
            asset.setChannelId(textOrNull(channelId));
            asset.setChannelName(textOrNull(channelName));
            asset.setStatus("ASSIGNED");
            asset.setApplicationId(applicationId);
            asset.setAssigneeId(assigneeId);
            asset.setAssigneeName(Objects.toString(assigneeName, "").trim());
            asset.setRemark("广告户申请办理入库");
            asset.setCreatedBy(operatorId);
            asset.setUpdatedBy(operatorId);
            boolean created = false;
            try {
                mapper.insertAsset(asset);
                created = true;
            } catch (DuplicateKeyException exception) {
                // 共享账户的申请关系已由办理流程先行写入，此处只复用唯一资产主记录。
                asset = mapper.findAssetByTypeAndCode("AD_ACCOUNT", accountId);
                if (asset == null) {
                    throw BusinessException.conflict("广告账户 " + accountId + " 的资产主记录读取失败，请重试");
                }
            }
            MediaAsset persisted = reveal(mapper.findAsset(asset.getId()));
            if (created) {
                String operatorName = textOrNull(mapper.findActiveUserName(operatorId));
                recordStocked(
                        persisted,
                        AUDIT_SOURCE_OPEN_ACCOUNT,
                        operatorId,
                        operatorName == null ? "系统" : operatorName);
                recordLifecycle(
                        "ASSIGNED",
                        persisted,
                        "开户办理后已分配使用人",
                        operatorId,
                        operatorName == null ? "系统" : operatorName);
            }
            registered.add(persisted);
        }
        return registered;
    }

    /** 修改资产；回收流程中的资产由回收模块独占，不能直接改写。 */
    @Transactional
    public MediaAsset updateAsset(Long id, AssetRequests.AssetSave request) {
        MediaAsset asset = requireAsset(id);
        if ("RETURN_PENDING".equals(asset.getStatus()))
            throw BusinessException.conflict("回收中的资产不能修改");
        validateImmutableAssetIdentity(asset, request);
        AssetAuditSnapshot before = auditSnapshot(asset);
        List<Long> sharedUsageUserIds = resolveSharedUsageUserIds(request);
        apply(asset, request, sharedUsageUserIds);
        Long userId = SecurityContextHelper.currentUserId();
        asset.setUpdatedBy(userId);
        mapper.updateAsset(asset);
        syncSharedUsageUsers(asset, sharedUsageUserIds, userId);
        MediaAsset updated = reveal(mapper.findAsset(id));
        recordUpdate(before, auditSnapshotFromRevealed(updated), updated, AUDIT_SOURCE_MANUAL_EDIT);
        return updated;
    }

    /**
     * 按显式字段白名单批量修改通用库存资产。
     *
     * <p>资产唯一标识和子类型不能批量覆盖；任一资产处于回收中或字段校验失败时，事务整体回滚。
     */
    @Transactional
    public List<MediaAsset> batchUpdateAssets(AssetRequests.AssetBatchUpdate request) {
        return batchUpdateAssets(request, AUDIT_SOURCE_BATCH_EDIT);
    }

    private List<MediaAsset> batchUpdateAssets(
            AssetRequests.AssetBatchUpdate request, String auditSource) {
        Set<AssetRequests.AssetBatchField> fields = request.changedFields();
        if (fields.isEmpty() && request.detailUpdates().isEmpty()) {
            throw BusinessException.validation("请至少选择一个要修改的字段");
        }
        validateBatchAssignment(request, fields);

        List<Long> assetIds = request.assetIds().stream().distinct().toList();
        List<BatchAssetUpdate> updates = new ArrayList<>();
        Map<Long, AssetAuditSnapshot> beforeById = new LinkedHashMap<>();
        String batchSubtype = null;
        for (Long assetId : assetIds) {
            MediaAsset asset = requireAsset(assetId);
            beforeById.put(assetId, auditSnapshot(asset));
            if ("RETURN_PENDING".equals(asset.getStatus())) {
                throw BusinessException.conflict("回收中的资产不能修改");
            }
            Map<String, String> details = decryptAssetDetails(asset.getSecretData());
            String subtype = resolveSubtype(asset, details);
            if (batchSubtype == null) {
                batchSubtype = subtype;
            } else if (!Objects.equals(batchSubtype, subtype)) {
                throw BusinessException.validation("一次只能批量修改同一种资产类型");
            }
            String identifierKey = IDENTIFIER_DETAIL_KEYS.get(subtype);
            if (identifierKey != null && request.detailUpdates().containsKey(identifierKey)) {
                throw BusinessException.validation("资产唯一标识不支持批量修改");
            }
            if (request.detailUpdates().containsKey("inventorySubtype")) {
                throw BusinessException.validation("资产类型不支持批量修改");
            }
            validateBatchDetailUpdates(subtype, request.detailUpdates());

            details.putAll(request.detailUpdates());
            applyBatchAssetFields(asset, request, fields, subtype, details);
            updates.add(new BatchAssetUpdate(asset, batchUsageUserIds(asset, request)));
        }

        Long operatorId = SecurityContextHelper.currentUserId();
        for (BatchAssetUpdate update : updates) {
            MediaAsset asset = update.asset();
            asset.setUpdatedBy(operatorId);
            mapper.updateAsset(asset);
            if (fields.contains(AssetRequests.AssetBatchField.INVENTORY_STATUS)) {
                syncSharedUsageUsers(asset, update.usageUserIds(), operatorId);
            }
        }
        List<MediaAsset> result =
                assetIds.stream().map(mapper::findAsset).map(this::reveal).toList();
        for (MediaAsset updated : result) {
            recordUpdate(
                    beforeById.get(updated.getId()),
                    auditSnapshotFromRevealed(updated),
                    updated,
                    auditSource);
        }
        return result;
    }

    /** 为电子表格弹窗返回最新的可见资产快照，避免使用列表中的过期数据。 */
    public List<MediaAsset> batchQueryAssets(AssetRequests.AssetBatchQuery request) {
        return request.assetIds().stream()
                .distinct()
                .map(this::requireAsset)
                .map(this::reveal)
                .toList();
    }

    /** 按资产类型与唯一标识精确返回电子表格可使用的最新资产快照。 */
    public List<MediaAsset> batchQueryAssetsByIdentifiers(
            AssetRequests.AssetIdentifierBatchQuery request) {
        String assetType = requireType(request.assetType());
        List<String> identifiers =
                request.identifiers().stream()
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();
        if (identifiers.isEmpty()) return List.of();
        return mapper.findAssetsByTypeAndCodes(assetType, identifiers).stream()
                .map(this::reveal)
                .toList();
    }

    /** 原子保存通用资产电子表格。新增与逐行修改复用现有创建、字段白名单和库存联动校验。 */
    @Transactional
    public AssetViews.AssetSpreadsheetSaveResult spreadsheetSave(
            AssetRequests.AssetSpreadsheetSave request) {
        List<Long> existingIds =
                request.rows().stream()
                        .map(AssetRequests.AssetSpreadsheetRow::assetId)
                        .filter(Objects::nonNull)
                        .toList();
        if (new HashSet<>(existingIds).size() != existingIds.size()) {
            throw BusinessException.validation("同一次保存中不能包含重复的资产 ID");
        }
        List<String> assetCodes =
                request.rows().stream()
                        .map(AssetRequests.AssetSpreadsheetRow::values)
                        .map(AssetRequests.AssetSave::assetCode)
                        .map(value -> Objects.toString(value, "").trim())
                        .filter(value -> !value.isEmpty())
                        .toList();
        if (new HashSet<>(assetCodes).size() != assetCodes.size()) {
            throw BusinessException.validation("同一次保存中不能包含重复的资产唯一标识");
        }

        int createdCount = 0;
        int updatedCount = 0;
        // 创建和批量更新已返回解密后的最新快照；直接复用，避免同一事务内的 MyBatis 缓存对象被重复解密。
        List<MediaAsset> savedItems = new ArrayList<>();
        for (AssetRequests.AssetSpreadsheetRow submittedRow : request.rows()) {
            AssetRequests.AssetSpreadsheetRow row =
                    normalizeSpreadsheetRow(submittedRow, request.subtype());
            if (row.assetId() == null) {
                if ("ad_account".equals(request.subtype())
                        || "AD_ACCOUNT".equals(row.values().assetType())) {
                    throw BusinessException.validation("广告户不支持粘贴新增，只能修改已有资产");
                }
                String assetType = requireType(row.values().assetType());
                String assetCode = textOrNull(row.values().assetCode());
                MediaAsset existing =
                        assetCode == null
                                ? null
                                : mapper.findAssetByTypeAndCode(assetType, assetCode);
                if (existing != null) {
                    savedItems.add(
                            updateSpreadsheetAsset(existing.getId(), row, request.subtype()));
                    updatedCount++;
                    continue;
                }
                try {
                    MediaAsset created = createAsset(row.values(), AUDIT_SOURCE_SPREADSHEET_CREATE);
                    savedItems.add(created);
                    createdCount++;
                } catch (BusinessException exception) {
                    // 粘贴确认后可能有并发写入；唯一约束冲突时重新读取并转为同一事务内更新。
                    MediaAsset concurrent =
                            assetCode == null
                                    ? null
                                    : mapper.findAssetByTypeAndCode(assetType, assetCode);
                    if (!"资产标识已存在".equals(exception.getMessage()) || concurrent == null) {
                        throw exception;
                    }
                    savedItems.add(
                            updateSpreadsheetAsset(concurrent.getId(), row, request.subtype()));
                    updatedCount++;
                }
                continue;
            }
            savedItems.add(updateSpreadsheetAsset(row.assetId(), row, request.subtype()));
            updatedCount++;
        }
        return new AssetViews.AssetSpreadsheetSaveResult(createdCount, updatedCount, savedItems);
    }

    /** Excel 批量处理不接收客户端库存状态，统一按占用主体推导并补齐必要的联动字段。 */
    private AssetRequests.AssetSpreadsheetRow normalizeSpreadsheetRow(
            AssetRequests.AssetSpreadsheetRow row, String subtype) {
        AssetRequests.AssetSave values = row.values();
        boolean pixel = "pixel".equalsIgnoreCase(subtype) || "PIXEL".equals(values.assetType());
        Long usageTeamId = row.usageTeamId() == null ? values.usageTeamId() : row.usageTeamId();
        List<Long> assigneeIds =
                row.assigneeIds() == null ? values.assigneeIds() : row.assigneeIds();
        List<Long> normalizedAssigneeIds =
                assigneeIds == null
                        ? values.assigneeId() == null
                                ? List.of()
                                : List.of(values.assigneeId())
                        : assigneeIds.stream().filter(Objects::nonNull).distinct().toList();

        String projectId = textOrNull(values.projectId());
        if (pixel && (projectId == null) != (usageTeamId == null)) {
            throw BusinessException.validation("所属项目和使用团队必须同时填写或同时留空");
        }
        String status =
                pixel
                        ? projectId == null ? "AVAILABLE" : "ASSIGNED"
                        : normalizedAssigneeIds.isEmpty() ? "AVAILABLE" : "ASSIGNED";
        Long assigneeId =
                pixel || normalizedAssigneeIds.isEmpty()
                        ? null
                        : normalizedAssigneeIds.getFirst();
        List<Long> savedAssigneeIds = pixel ? List.of() : normalizedAssigneeIds;

        AssetRequests.AssetSave normalizedValues =
                new AssetRequests.AssetSave(
                        values.assetType(),
                        values.assetName(),
                        values.assetCode(),
                        values.projectId(),
                        values.projectName(),
                        values.channelId(),
                        values.channelName(),
                        values.secretData(),
                        values.remark(),
                        status,
                        assigneeId,
                        savedAssigneeIds,
                        usageTeamId);
        Set<AssetRequests.AssetBatchField> changedFields =
                new HashSet<>(row.changedFields());
        changedFields.remove(AssetRequests.AssetBatchField.INVENTORY_STATUS);
        changedFields.remove(AssetRequests.AssetBatchField.USAGE_USERS);
        if (pixel) {
            changedFields.add(AssetRequests.AssetBatchField.PROJECT);
            changedFields.add(AssetRequests.AssetBatchField.USAGE_TEAM);
        } else {
            changedFields.add(AssetRequests.AssetBatchField.INVENTORY_STATUS);
            if (!savedAssigneeIds.isEmpty()) {
                changedFields.add(AssetRequests.AssetBatchField.USAGE_USERS);
            }
        }
        return new AssetRequests.AssetSpreadsheetRow(
                row.assetId(),
                normalizedValues,
                changedFields,
                row.detailUpdates(),
                savedAssigneeIds,
                usageTeamId);
    }

    private MediaAsset updateSpreadsheetAsset(
            Long assetId, AssetRequests.AssetSpreadsheetRow row, String subtype) {
        MediaAsset current = requireAsset(assetId);
        String currentSubtype =
                resolveSubtype(current, decryptAssetDetails(current.getSecretData()));
        if (!Objects.equals(currentSubtype, subtype)) {
            throw BusinessException.validation("一次只能保存同一种资产类型");
        }
        Map<String, String> detailUpdates = new LinkedHashMap<>(row.detailUpdates());
        String identifierKey = IDENTIFIER_DETAIL_KEYS.get(subtype);
        if (identifierKey != null) detailUpdates.remove(identifierKey);
        detailUpdates.remove("inventorySubtype");
        AssetRequests.AssetSave values = row.values();
        return batchUpdateAssets(
                        new AssetRequests.AssetBatchUpdate(
                                List.of(assetId),
                                row.changedFields(),
                                detailUpdates,
                                values.channelId(),
                                values.channelName(),
                                values.projectId(),
                                values.projectName(),
                                values.remark(),
                                values.status(),
                                values.assigneeId(),
                                row.assigneeIds() == null
                                        ? values.assigneeIds()
                                        : row.assigneeIds(),
                                row.usageTeamId()),
                        AUDIT_SOURCE_EXCEL_BATCH)
                .getFirst();
    }

    /**
     * 为已分配广告账户直接指定实际使用人。
     *
     * <p>广告账户可通过申请增加共享使用人；此处只更新资产主记录的直接指定人，列表查询会将两类 使用关系合并展示。非已分配账户不允许保存，避免为库存账户建立无效的人员关系。
     */
    @Transactional
    public MediaAsset updateAdAccountUsageUser(Long id, Long usageUserId) {
        MediaAsset asset = requireAsset(id);
        if (!"AD_ACCOUNT".equals(asset.getAssetType()))
            throw BusinessException.validation("仅广告账户支持指定使用人");
        if (!"ASSIGNED".equals(asset.getStatus()))
            throw BusinessException.conflict("仅已分配的广告账户可以指定使用人");
        String usageUserName = mapper.findActiveUserName(usageUserId);
        if (usageUserName == null || usageUserName.isBlank())
            throw BusinessException.validation("请选择有效使用人");

        asset.setAssigneeId(usageUserId);
        asset.setAssigneeName(usageUserName);
        asset.setUpdatedBy(SecurityContextHelper.currentUserId());
        mapper.updateAsset(asset);
        MediaAsset updated = reveal(mapper.findAsset(id));
        recordLifecycle("ASSIGNED", updated, "已调整实际使用人");
        return updated;
    }

    /** 删除未分配资产。 */
    @Transactional
    public void deleteAsset(Long id) {
        MediaAsset asset = requireAsset(id);
        if (mapper.softDeleteAsset(
                        id, System.currentTimeMillis(), SecurityContextHelper.currentUserId())
                != 1) throw BusinessException.conflict("仅可删除未分配资产");
        recordLifecycle("DELETED", asset, "资产已归档删除");
    }

    /** 资产生命周期详情仅返回身份、使用区间与脱敏事件，绝不返回原始凭据。 */
    public AssetViews.AssetLifecycleDetail lifecycle(Long id) {
        if (lifecycleService == null) throw BusinessException.conflict("资产生命周期服务尚未配置");
        return lifecycleService.detail(reveal(requireAsset(id)));
    }

    /** 动态审批办理完成库存分配后调用，保证分配动作与生命周期账本同一事务提交。 */
    public void recordLifecycleAllocation(Long assetId) {
        recordLifecycle("ASSIGNED", reveal(requireAsset(assetId)), "审批办理后发放资产");
    }

    private void recordLifecycle(String eventType, MediaAsset asset, String description) {
        if (lifecycleService != null) lifecycleService.record(eventType, asset, description);
    }

    private void recordLifecycle(
            String eventType,
            MediaAsset asset,
            String description,
            Long actorId,
            String actorName) {
        if (lifecycleService == null) return;
        lifecycleService.record(
                eventType,
                asset.getId(),
                asset.getStatus(),
                asset.getApplicationId(),
                actorId,
                actorName,
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                asset.getUsageTeam() == null || asset.getUsageTeam().isBlank()
                        ? asset.getAssigneeDepartmentName()
                        : asset.getUsageTeam(),
                description);
    }

    /** 按最终持久化结果保存不可变的入库资料快照，空字段不会写入事件。 */
    private void recordStocked(MediaAsset asset, String updateSource) {
        if (lifecycleService == null) return;
        lifecycleService.record(
                "STOCKED",
                asset,
                "资产已入库",
                updateSource,
                initialChanges(auditSnapshotFromRevealed(asset)));
    }

    private void recordStocked(
            MediaAsset asset, String updateSource, Long actorId, String actorName) {
        if (lifecycleService == null) return;
        lifecycleService.record(
                "STOCKED",
                asset.getId(),
                asset.getStatus(),
                asset.getApplicationId(),
                actorId,
                actorName,
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                asset.getUsageTeam() == null || asset.getUsageTeam().isBlank()
                        ? asset.getAssigneeDepartmentName()
                        : asset.getUsageTeam(),
                "资产已入库",
                updateSource,
                initialChanges(auditSnapshotFromRevealed(asset)));
    }

    /** 在业务事务内按最终持久化值写入一条资料更新事件；无实际差异时不生成事件。 */
    private void recordUpdate(
            AssetAuditSnapshot before,
            AssetAuditSnapshot after,
            MediaAsset asset,
            String updateSource) {
        if (lifecycleService == null || before == null || after == null) return;
        List<AssetViews.LifecycleFieldChange> changes = auditChanges(before, after);
        if (changes.isEmpty()) return;
        lifecycleService.record("UPDATED", asset, "资产资料已更新", updateSource, changes);
    }

    private AssetAuditSnapshot auditSnapshot(MediaAsset asset) {
        return new AssetAuditSnapshot(
                asset.getAssetType(),
                asset.getAssetName(),
                asset.getAssetCode(),
                asset.getChannelId(),
                asset.getChannelName(),
                asset.getProjectId(),
                asset.getProjectName(),
                asset.getUsageTeam(),
                asset.getStatus(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getUsageUserIds(),
                asset.getUsageUserNames(),
                asset.getRemark(),
                new LinkedHashMap<>(decryptAssetDetails(asset.getSecretData())));
    }

    private AssetAuditSnapshot auditSnapshotFromRevealed(MediaAsset asset) {
        return new AssetAuditSnapshot(
                asset.getAssetType(),
                asset.getAssetName(),
                asset.getAssetCode(),
                asset.getChannelId(),
                asset.getChannelName(),
                asset.getProjectId(),
                asset.getProjectName(),
                asset.getUsageTeam(),
                asset.getStatus(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getUsageUserIds(),
                asset.getUsageUserNames(),
                asset.getRemark(),
                new LinkedHashMap<>(assetDetails(asset.getSecretData())));
    }

    List<AssetViews.LifecycleFieldChange> initialChanges(AssetAuditSnapshot after) {
        AssetAuditSnapshot empty =
                new AssetAuditSnapshot(
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        new LinkedHashMap<>());
        List<AssetViews.LifecycleFieldChange> changes = new ArrayList<>();
        addAuditChange(
                changes,
                "assetType",
                "资产类型",
                auditText(null),
                auditReference(after.assetType(), assetTypeLabel(after.assetType())));
        String subtype = textOrNull(after.details().get("inventorySubtype"));
        addAuditChange(
                changes,
                "assetSubtype",
                "资产子类型",
                auditText(null),
                auditReference(subtype, subtype));
        changes.addAll(auditChanges(empty, after));
        return changes;
    }

    private String assetTypeLabel(String assetType) {
        return switch (Objects.toString(assetType, "")) {
            case "AD_ACCOUNT" -> "广告账户";
            case "PERSONAL" -> "个人号";
            case "BM" -> "BM";
            case "PIXEL" -> "像素";
            case "TG" -> "TG";
            case "PAGE" -> "主页";
            case "COMPUTER" -> "电脑";
            case "MOBILE" -> "手机";
            case "STATIC_IP" -> "静态 IP";
            case "EMAIL" -> "邮箱";
            default -> textOrNull(assetType);
        };
    }

    List<AssetViews.LifecycleFieldChange> auditChanges(
            AssetAuditSnapshot before, AssetAuditSnapshot after) {
        List<AssetViews.LifecycleFieldChange> changes = new ArrayList<>();
        addAuditChange(
                changes,
                "assetName",
                "资产名称",
                auditText(before.assetName()),
                auditText(after.assetName()));
        addAuditChange(
                changes,
                "assetCode",
                "资产标识",
                auditText(before.assetCode()),
                auditText(after.assetCode()));
        addAuditChange(
                changes,
                "channel",
                "渠道",
                auditReference(before.channelId(), before.channelName()),
                auditReference(after.channelId(), after.channelName()));
        addAuditChange(
                changes,
                "project",
                "项目",
                auditReference(before.projectId(), before.projectName()),
                auditReference(after.projectId(), after.projectName()));
        addAuditChange(
                changes,
                "usageTeam",
                "使用团队",
                auditReference(null, before.usageTeam()),
                auditReference(null, after.usageTeam()));
        addAuditChange(
                changes,
                "status",
                "库存状态",
                auditStatus(before.status()),
                auditStatus(after.status()));
        addAuditChange(changes, "usageUsers", "使用人", auditUsers(before), auditUsers(after));
        addAuditChange(
                changes, "remark", "备注", auditText(before.remark()), auditText(after.remark()));

        Set<String> detailKeys = new java.util.TreeSet<>();
        detailKeys.addAll(before.details().keySet());
        detailKeys.addAll(after.details().keySet());
        detailKeys.remove("inventorySubtype");
        for (String key : detailKeys) {
            String oldValue = textOrNull(before.details().get(key));
            String newValue = textOrNull(after.details().get(key));
            if (Objects.equals(oldValue, newValue)) continue;
            String label = AUDIT_DETAIL_LABELS.getOrDefault(key, key);
            if (SENSITIVE_DETAIL_KEYS.contains(key)) {
                changes.add(
                        new AssetViews.LifecycleFieldChange(
                                key,
                                label,
                                auditSecret(oldValue != null, false),
                                auditSecret(
                                        newValue != null, oldValue != null && newValue != null)));
            } else {
                addAuditChange(
                        changes,
                        key,
                        label,
                        auditOption(key, oldValue),
                        auditOption(key, newValue));
            }
        }
        return changes;
    }

    private void addAuditChange(
            List<AssetViews.LifecycleFieldChange> changes,
            String key,
            String label,
            AssetViews.LifecycleChangeValue before,
            AssetViews.LifecycleChangeValue after) {
        if (!Objects.equals(before, after)) {
            changes.add(new AssetViews.LifecycleFieldChange(key, label, before, after));
        }
    }

    private AssetViews.LifecycleChangeValue auditText(String value) {
        return new AssetViews.LifecycleChangeValue(textOrNull(value), List.of(), false);
    }

    private AssetViews.LifecycleChangeValue auditReference(String id, String name) {
        String normalizedId = textOrNull(id);
        String normalizedName = textOrNull(name);
        List<AssetViews.LifecycleValueReference> references =
                normalizedId == null && normalizedName == null
                        ? List.of()
                        : List.of(
                                new AssetViews.LifecycleValueReference(
                                        normalizedId, normalizedName));
        return new AssetViews.LifecycleChangeValue(normalizedName, references, false);
    }

    private AssetViews.LifecycleChangeValue auditStatus(String status) {
        String normalized = textOrNull(status);
        String label =
                switch (normalized == null ? "" : normalized) {
                    case "AVAILABLE" -> "可用";
                    case "ASSIGNED" -> "已分配";
                    case "RETURN_PENDING" -> "待回收";
                    case "DISABLED" -> "已停用";
                    default -> normalized;
                };
        return auditReference(normalized, label);
    }

    private AssetViews.LifecycleChangeValue auditUsers(AssetAuditSnapshot snapshot) {
        List<String> ids = splitAuditValues(snapshot.usageUserIds());
        List<String> names = splitAuditValues(snapshot.usageUserNames());
        if (ids.isEmpty() && snapshot.assigneeId() != null)
            ids = List.of(String.valueOf(snapshot.assigneeId()));
        if (names.isEmpty() && textOrNull(snapshot.assigneeName()) != null)
            names = List.of(snapshot.assigneeName());
        List<AssetViews.LifecycleValueReference> references = new ArrayList<>();
        int size = Math.max(ids.size(), names.size());
        for (int index = 0; index < size; index++) {
            references.add(
                    new AssetViews.LifecycleValueReference(
                            index < ids.size() ? ids.get(index) : null,
                            index < names.size() ? names.get(index) : null));
        }
        return new AssetViews.LifecycleChangeValue(
                names.isEmpty() ? null : String.join("、", names), references, false);
    }

    private List<String> splitAuditValues(String value) {
        String normalized = textOrNull(value);
        if (normalized == null) return List.of();
        return Arrays.stream(normalized.split("[,，、]"))
                .map(this::textOrNull)
                .filter(Objects::nonNull)
                .toList();
    }

    private AssetViews.LifecycleChangeValue auditSecret(boolean set, boolean replaced) {
        return new AssetViews.LifecycleChangeValue(
                set ? replaced ? "已重新设置" : "已设置" : null, List.of(), true);
    }

    private AssetViews.LifecycleChangeValue auditOption(String key, String value) {
        String normalized = textOrNull(value);
        if (normalized == null) return auditText(null);
        String label =
                switch (key + ":" + normalized.toLowerCase(Locale.ROOT)) {
                    case "gender:male" -> "男";
                    case "gender:female" -> "女";
                    case "supplierRemoved:true" -> "是";
                    case "supplierRemoved:false" -> "否";
                    default -> null;
                };
        return label == null ? auditText(normalized) : auditReference(normalized, label);
    }

    /** 查询审批配置。 */
    public List<ApprovalConfig> configs() {
        return mapper.findConfigs();
    }

    /** 保存资产类型的审批配置。 */
    @Transactional
    public ApprovalConfig saveConfig(AssetRequests.ApprovalConfigSave request) {
        String type = requireType(request.assetType());
        if (mapper.countActiveUser(request.approverId()) != 1)
            throw BusinessException.conflict("审批人不存在或已停用");
        ApprovalConfig config = new ApprovalConfig();
        config.setAssetType(type);
        config.setApproverId(request.approverId());
        config.setApproverName(request.approverName().trim());
        config.setCcUserIds(request.ccUserIds());
        mapper.upsertConfig(config, SecurityContextHelper.currentUserId());
        return mapper.findConfig(type);
    }

    /** 软删除审批配置，已提交申请继续使用其历史快照。 */
    @Transactional
    public void deleteApprovalConfig(Long id) {
        if (mapper.softDeleteConfig(
                        id, System.currentTimeMillis(), SecurityContextHelper.currentUserId())
                != 1) throw BusinessException.notFound("审批配置");
    }

    /** 查询审批配置分组，包含暂时没有审批配置的空分组。 */
    /** 新建审批配置分组，新分组默认排在现有分组末尾。 */
    /** 保存完整分组顺序；拒绝缺失、重复或已过期的分组 ID，防止并发覆盖。 */
    /** 删除空分组；分组内仍有审批配置时必须先移动配置。 */
    /** 获取有效审批分组，供审批配置保存时校验并使用服务端标准名称。 */
    /** 提交当前用户的资源申请。 */
    @Transactional
    public AssetApplication apply(AssetRequests.ApplicationCreate request) {
        String type = requireType(request.assetType());
        ApprovalConfig config = mapper.findConfig(type);
        if (config == null) throw BusinessException.conflict("该资产类型尚未配置审批人");
        CurrentUser user = SecurityContextHelper.currentUser();
        AssetApplication application = new AssetApplication();
        application.setApplicationNo(
                "AST"
                        + LocalDateTime.now()
                                .format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS")));
        application.setAssetType(type);
        application.setTitle(request.title().trim());
        application.setQuantity(request.quantity());
        application.setReason(request.reason().trim());
        application.setRequesterId(user.userId());
        application.setRequesterName(user.displayName());
        application.setApproverId(config.getApproverId());
        application.setApproverName(config.getApproverName());
        mapper.insertApplication(application, user.userId());
        mapper.insertApprovalLog(
                application.getId(),
                "SUBMITTED",
                user.userId(),
                user.displayName(),
                request.reason());
        return mapper.findApplication(application.getId());
    }

    /** 查询当前用户发起的申请。 */
    public List<AssetApplication> myApplications() {
        return mapper.findApplications(SecurityContextHelper.currentUserId(), null);
    }

    /** 查询当前用户负责审批的申请。 */
    public List<AssetApplication> approvals() {
        return mapper.findApplications(null, SecurityContextHelper.currentUserId());
    }

    /** 审批通过并原子分配足量库存。 */
    @Transactional
    public AssetApplication approve(Long id, AssetRequests.Decision request) {
        AssetApplication application = requirePendingApprover(id);
        List<MediaAsset> assets =
                mapper.lockAvailableAssets(application.getAssetType(), application.getQuantity());
        if (assets.size() < application.getQuantity())
            throw BusinessException.conflict("可用资产库存不足，当前仅有" + assets.size() + "个");
        Long operatorId = SecurityContextHelper.currentUserId();
        for (MediaAsset asset : assets)
            mapper.assignAsset(
                    asset.getId(),
                    id,
                    application.getRequesterId(),
                    application.getRequesterName(),
                    operatorId);
        decide(application, "APPROVED", request.remark());
        return mapper.findApplication(id);
    }

    /** 驳回资源申请。 */
    @Transactional
    public AssetApplication reject(Long id, AssetRequests.Decision request) {
        AssetApplication application = requirePendingApprover(id);
        decide(application, "REJECTED", request.remark());
        return mapper.findApplication(id);
    }

    private void decide(AssetApplication application, String status, String remark) {
        CurrentUser user = SecurityContextHelper.currentUser();
        if (mapper.decideApplication(application.getId(), status, remark, user.userId()) != 1)
            throw BusinessException.conflict("申请状态已变化，请刷新后重试");
        mapper.insertApprovalLog(
                application.getId(), status, user.userId(), user.displayName(), remark);
    }

    private AssetApplication requirePendingApprover(Long id) {
        AssetApplication value = mapper.findApplication(id);
        if (value == null) throw BusinessException.notFound("申请单");
        if (!"PENDING".equals(value.getStatus())) throw BusinessException.conflict("申请已处理");
        if (!SecurityContextHelper.currentUserId().equals(value.getApproverId()))
            throw BusinessException.conflict("当前用户不是该申请审批人");
        return value;
    }

    private MediaAsset requireAsset(Long id) {
        MediaAsset value = mapper.findAsset(id);
        if (value == null) throw BusinessException.notFound("资产");
        return value;
    }

    private void validateBatchAssignment(
            AssetRequests.AssetBatchUpdate request, Set<AssetRequests.AssetBatchField> fields) {
        if (fields.contains(AssetRequests.AssetBatchField.USAGE_USERS)
                && (!fields.contains(AssetRequests.AssetBatchField.INVENTORY_STATUS)
                        || !"ASSIGNED".equalsIgnoreCase(textOrNull(request.status())))) {
            throw BusinessException.validation("修改使用人时必须同时将库存状态设为已分配");
        }
        if (!fields.contains(AssetRequests.AssetBatchField.INVENTORY_STATUS)) return;

        String status = textOrNull(request.status());
        if (status == null) throw BusinessException.validation("请选择库存状态");
        if ("ASSIGNED".equalsIgnoreCase(status)
                && (!fields.contains(AssetRequests.AssetBatchField.USAGE_USERS)
                        || (request.assigneeId() == null
                                && (request.assigneeIds() == null
                                        || request.assigneeIds().isEmpty())))) {
            throw BusinessException.validation("已分配状态必须指定至少一位使用人");
        }
    }

    private void validateBatchDetailUpdates(String subtype, Map<String, String> updates) {
        Set<String> editableKeys = BATCH_EDITABLE_DETAIL_KEYS.get(subtype);
        if (editableKeys == null || !editableKeys.containsAll(updates.keySet())) {
            throw BusinessException.validation("包含当前资产类型不支持批量修改的字段");
        }
        Set<String> requiredKeys = REQUIRED_BATCH_DETAIL_KEYS.getOrDefault(subtype, Set.of());
        for (String key : requiredKeys) {
            if (updates.containsKey(key) && textOrNull(updates.get(key)) == null) {
                throw BusinessException.validation("必填字段不允许清空");
            }
        }
    }

    private Map<String, String> decryptAssetDetails(String encryptedSecretData) {
        if (encryptedSecretData == null || encryptedSecretData.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            String secretData = secretCipher.decrypt(encryptedSecretData);
            Map<String, Object> values =
                    JSON_MAPPER.readValue(secretData, new TypeReference<Map<String, Object>>() {});
            Map<String, String> details = new LinkedHashMap<>();
            values.forEach((key, value) -> details.put(key, Objects.toString(value, "")));
            return details;
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("资产明细格式无效，无法批量修改");
        }
    }

    private void applyBatchAssetFields(
            MediaAsset asset,
            AssetRequests.AssetBatchUpdate request,
            Set<AssetRequests.AssetBatchField> fields,
            String subtype,
            Map<String, String> details) {
        if (!request.detailUpdates().isEmpty()) {
            asset.setSecretData(secretCipher.encrypt(serializeAssetDetails(details)));
            String nameKey = NAME_DETAIL_KEYS.get(subtype);
            if (nameKey != null && request.detailUpdates().containsKey(nameKey)) {
                String name = textOrNull(details.get(nameKey));
                asset.setAssetName(name == null ? asset.getAssetCode() : name);
            }
        }
        if (fields.contains(AssetRequests.AssetBatchField.CHANNEL)) {
            ChannelReference channel =
                    requireBatchChannel(request.channelId(), request.channelName());
            asset.setChannelId(String.valueOf(channel.id()));
            asset.setChannelName(channel.channelName());
            asset.setProjectId(String.valueOf(channel.id()));
            asset.setProjectName(channel.channelName());
        }
        if (fields.contains(AssetRequests.AssetBatchField.PROJECT)) {
            applyBatchPixelProject(asset, request);
        }
        if (fields.contains(AssetRequests.AssetBatchField.USAGE_TEAM)) {
            applyBatchPixelUsageTeam(asset, request);
        }
        if ("PIXEL".equals(asset.getAssetType())
                && (fields.contains(AssetRequests.AssetBatchField.PROJECT)
                        || fields.contains(AssetRequests.AssetBatchField.USAGE_TEAM))) {
            synchronizeBatchPixelAssignment(asset);
        }
        if (fields.contains(AssetRequests.AssetBatchField.REMARK)) {
            asset.setRemark(textOrNull(request.remark()));
        }
        if (fields.contains(AssetRequests.AssetBatchField.INVENTORY_STATUS)) {
            List<Long> usageUserIds = batchUsageUserIds(asset, request);
            applyManualAssignment(
                    asset,
                    request.status(),
                    usageUserIds.isEmpty() ? request.assigneeId() : usageUserIds.getFirst());
        }
    }

    private ChannelReference requireBatchChannel(String channelId, String channelName) {
        String normalizedId = textOrNull(channelId);
        if (normalizedId != null) {
            try {
                ChannelReference channel =
                        mapper.findActiveChannelById(Long.parseLong(normalizedId));
                if (channel == null) {
                    throw BusinessException.validation("渠道不存在或已停用");
                }
                return channel;
            } catch (NumberFormatException exception) {
                throw BusinessException.validation("渠道标识无效");
            }
        }
        String normalizedName = textOrNull(channelName);
        if (normalizedName == null) throw BusinessException.validation("请选择渠道");
        List<ChannelReference> channels = mapper.findActiveChannelsByName(normalizedName);
        if (channels.isEmpty()) throw BusinessException.validation("渠道不存在或已停用");
        if (channels.size() > 1) throw BusinessException.validation("渠道名称重复，请重新选择");
        return channels.getFirst();
    }

    /** 批量调整像素项目归属时仅覆盖项目，其他归属字段保持原值。 */
    private void applyBatchPixelProject(MediaAsset asset, AssetRequests.AssetBatchUpdate request) {
        if (!"PIXEL".equals(asset.getAssetType())) {
            throw BusinessException.validation("仅像素资产支持修改所属项目");
        }
        String projectId = textOrNull(request.projectId());
        String projectName = textOrNull(request.projectName());
        if (projectId == null) {
            asset.setProjectId(null);
            asset.setProjectName(null);
            return;
        }
        if (projectName == null || mapper.countActiveProject(projectId, projectName) != 1) {
            throw BusinessException.validation("请选择有效的所属项目");
        }
        asset.setProjectId(projectId);
        asset.setProjectName(projectName);
    }

    /** 批量调整像素使用团队时仅覆盖团队名称，其他归属字段保持原值。 */
    private void applyBatchPixelUsageTeam(
            MediaAsset asset, AssetRequests.AssetBatchUpdate request) {
        if (!"PIXEL".equals(asset.getAssetType())) {
            throw BusinessException.validation("仅像素资产支持修改使用团队");
        }
        if (request.usageTeamId() == null) {
            asset.setUsageTeam(null);
            return;
        }
        String usageTeam = mapper.findActiveDepartmentName(request.usageTeamId());
        if (usageTeam == null || usageTeam.isBlank()) {
            throw BusinessException.validation("请选择有效的使用团队");
        }
        asset.setUsageTeam(usageTeam);
    }

    /** 像素的库存状态由项目归属唯一决定，批量编辑必须与单条编辑保持相同口径。 */
    private void synchronizeBatchPixelAssignment(MediaAsset asset) {
        if (textOrNull(asset.getProjectId()) == null) {
            asset.setProjectId(null);
            asset.setProjectName(null);
            asset.setUsageTeam(null);
            asset.setStatus("AVAILABLE");
        } else {
            if (textOrNull(asset.getUsageTeam()) == null) {
                throw BusinessException.validation("请选择有效的使用团队");
            }
            asset.setStatus("ASSIGNED");
        }
        asset.setAssigneeId(null);
        asset.setAssigneeName(null);
    }

    private List<Long> batchUsageUserIds(MediaAsset asset, AssetRequests.AssetBatchUpdate request) {
        if (!"ASSIGNED".equalsIgnoreCase(textOrNull(request.status()))) return List.of();
        if (supportsSharedUsageUsers(asset.getAssetType())) {
            List<Long> userIds =
                    request.assigneeIds() == null
                            ? new ArrayList<>()
                            : new ArrayList<>(request.assigneeIds());
            if (userIds.isEmpty() && request.assigneeId() != null) {
                userIds.add(request.assigneeId());
            }
            return userIds.stream().distinct().toList();
        }
        return request.assigneeId() == null ? List.of() : List.of(request.assigneeId());
    }

    private String serializeAssetDetails(Map<String, String> details) {
        try {
            return JSON_MAPPER.writeValueAsString(details);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("资产明细转换失败");
        }
    }

    private MediaAsset apply(
            MediaAsset asset, AssetRequests.AssetSave request, List<Long> sharedUsageUserIds) {
        String assetType = requireType(request.assetType());
        String assetName = request.assetName().trim();
        String assetCode = resolveSaveAssetCode(assetType, assetName, request.assetCode());
        asset.setAssetType(assetType);
        asset.setAssetName(assetName);
        asset.setAssetCode(assetCode);
        if ("PIXEL".equals(assetType)) {
            // 像素的占用关系以项目为唯一依据，不建立使用人或共享使用人关联。
            String projectId = textOrNull(request.projectId());
            String projectName = projectId == null ? null : textOrNull(request.projectName());
            Long usageTeamId = projectId == null ? null : request.usageTeamId();
            String usageTeam =
                    usageTeamId == null ? null : mapper.findActiveDepartmentName(usageTeamId);
            if (projectId != null) {
                if (projectName == null || mapper.countActiveProject(projectId, projectName) != 1) {
                    throw BusinessException.validation("请选择有效的所属项目");
                }
                if (usageTeam == null || usageTeam.isBlank()) {
                    throw BusinessException.validation("请选择有效的使用团队");
                }
            }
            asset.setProjectId(projectId);
            asset.setProjectName(projectName);
            asset.setChannelId(null);
            asset.setChannelName(null);
            asset.setUsageTeam(usageTeam);
            asset.setApplicationId(null);
            asset.setAssigneeId(null);
            asset.setAssigneeName(null);
            asset.setStatus(projectId == null ? "AVAILABLE" : "ASSIGNED");
            asset.setSecretData(
                    request.secretData() == null || request.secretData().isBlank()
                            ? null
                            : secretCipher.encrypt(request.secretData()));
            asset.setRemark(request.remark());
            return asset;
        }
        String channelId = textOrNull(request.channelId());
        String channelName = textOrNull(request.channelName());
        if (channelId == null) channelId = textOrNull(request.projectId());
        if (channelName == null) channelName = textOrNull(request.projectName());
        // 手工录入保留名称快照兼容；导入场景则在 resolveImportChannel 中严格校验。
        if (channelName != null && channelId == null) {
            ChannelReference channel = resolveManualChannel(channelName);
            channelId = channel.id() == null ? null : String.valueOf(channel.id());
            channelName = channel.channelName();
        } else if (channelName == null) {
            channelId = null;
        }
        asset.setChannelId(channelId);
        asset.setChannelName(channelName);
        // 迁移期镜像旧项目字段，确保历史审批分配逻辑仍可识别同一渠道归属。
        asset.setProjectId(channelId);
        asset.setProjectName(channelName);
        asset.setSecretData(
                request.secretData() == null || request.secretData().isBlank()
                        ? null
                        : secretCipher.encrypt(request.secretData()));
        asset.setRemark(request.remark());
        Long assigneeId =
                supportsSharedUsageUsers(asset.getAssetType()) && !sharedUsageUserIds.isEmpty()
                        ? sharedUsageUserIds.getFirst()
                        : request.assigneeId();
        applyManualAssignment(asset, request.status(), assigneeId);
        return asset;
    }

    /** 单条编辑只能修改资产资料，主类型、业务子类型和唯一标识必须保持创建时的身份。 */
    private void validateImmutableAssetIdentity(MediaAsset asset, AssetRequests.AssetSave request) {
        String requestedAssetType = requireType(request.assetType());
        if (!Objects.equals(asset.getAssetType(), requestedAssetType)) {
            throw BusinessException.validation("资产类型创建后不可修改");
        }

        Map<String, String> currentDetails = decryptAssetDetails(asset.getSecretData());
        String currentSubtype = resolveSubtype(asset, currentDetails);
        Map<String, String> requestedDetails = assetDetails(request.secretData());
        String requestedSubtype = textOrNull(requestedDetails.get("inventorySubtype"));
        if (!Objects.equals(currentSubtype, requestedSubtype)) {
            throw BusinessException.validation("资产子类型创建后不可修改");
        }

        String requestedAssetCode =
                resolveSaveAssetCode(
                        requestedAssetType, request.assetName().trim(), request.assetCode());
        if (!Objects.equals(asset.getAssetCode(), requestedAssetCode)) {
            throw BusinessException.validation("资产唯一标识创建后不可修改");
        }
        String identifierKey = IDENTIFIER_DETAIL_KEYS.get(currentSubtype);
        String requestedDetailIdentifier =
                identifierKey == null ? null : textOrNull(requestedDetails.get(identifierKey));
        if (identifierKey != null
                && !Objects.equals(asset.getAssetCode(), requestedDetailIdentifier)) {
            throw BusinessException.validation("资产唯一标识创建后不可修改");
        }
    }

    private String resolveSaveAssetCode(String assetType, String assetName, String assetCode) {
        String normalizedCode = textOrNull(assetCode);
        // 主页 ID 可选；服务端以必填主页名称兜底，其他资产类型仍必须提供唯一标识。
        if (normalizedCode == null && "PAGE".equals(assetType)) normalizedCode = assetName;
        if (normalizedCode == null) throw BusinessException.validation("资产唯一标识不能为空");
        return normalizedCode;
    }

    private void requireUniqueActiveDepartment(String departmentName) {
        List<Long> departmentIds = mapper.findActiveDepartmentIdsByName(departmentName);
        if (departmentIds.isEmpty()) throw BusinessException.validation("使用团队不存在或已停用");
        if (departmentIds.size() > 1) {
            throw BusinessException.validation("使用团队重名，请在系统部门中保留唯一名称");
        }
    }

    /** 广告账户的使用人使用关联表保存，其余资产继续沿用单使用人字段。 */
    private List<Long> resolveSharedUsageUserIds(AssetRequests.AssetSave request) {
        if (!supportsSharedUsageUsers(request.assetType())) return List.of();
        List<Long> selectedUserIds =
                request.assigneeIds() == null
                        ? new ArrayList<>()
                        : new ArrayList<>(request.assigneeIds());
        if (selectedUserIds.isEmpty() && request.assigneeId() != null) {
            selectedUserIds.add(request.assigneeId());
        }
        return selectedUserIds.stream().distinct().toList();
    }

    private void syncSharedUsageUsers(MediaAsset asset, List<Long> userIds, Long operatorId) {
        if (!supportsSharedUsageUsers(asset.getAssetType())) return;
        mapper.deactivatePixelUsageUsers(asset.getId(), System.currentTimeMillis(), operatorId);
        if (!"ASSIGNED".equals(asset.getStatus())) return;
        for (Long userId : userIds) {
            String userName = mapper.findActiveUserName(userId);
            if (userName == null || userName.isBlank())
                throw BusinessException.validation("请选择有效使用人");
            mapper.upsertPixelUsageUser(asset.getId(), userId, userName, operatorId);
        }
    }

    private boolean supportsSharedUsageUsers(String assetType) {
        return "AD_ACCOUNT".equalsIgnoreCase(assetType);
    }

    /** 办理像素申请时追加共享使用人，不覆盖该像素已存在的其他授权。 */
    public void addPixelUsageUser(Long assetId, Long userId, Long operatorId) {
        MediaAsset asset = requireAsset(assetId);
        if (!"PIXEL".equals(asset.getAssetType())) return;
        String validUserName = mapper.findActiveUserName(userId);
        if (validUserName == null || validUserName.isBlank())
            throw BusinessException.validation("请选择有效使用人");
        mapper.upsertPixelUsageUser(assetId, userId, validUserName, operatorId);
    }

    /** 校验手工分配状态，并使用系统用户表中的名称保存资产使用人。 */
    private void applyManualAssignment(MediaAsset asset, String requestedStatus, Long assigneeId) {
        String status =
                requestedStatus == null || requestedStatus.isBlank()
                        ? "AVAILABLE"
                        : requestedStatus.trim().toUpperCase(Locale.ROOT);
        if (!Set.of("AVAILABLE", "ASSIGNED", "DISABLED").contains(status))
            throw BusinessException.validation("库存状态不受支持");

        asset.setStatus(status);
        if (!"ASSIGNED".equals(status)) {
            asset.setApplicationId(null);
            asset.setAssigneeId(null);
            asset.setAssigneeName(null);
            return;
        }
        if (assigneeId == null || assigneeId <= 0) throw BusinessException.validation("请选择使用人");
        String assigneeName = mapper.findActiveUserName(assigneeId);
        if (assigneeName == null || assigneeName.isBlank())
            throw BusinessException.validation("请选择有效使用人");
        asset.setAssigneeId(assigneeId);
        asset.setAssigneeName(assigneeName);
    }

    private List<MediaAsset> reveal(List<MediaAsset> assets) {
        assets.forEach(this::reveal);
        return assets;
    }

    private MediaAsset reveal(MediaAsset asset) {
        if (asset != null && asset.getSecretData() != null && !asset.getSecretData().isBlank())
            asset.setSecretData(secretCipher.decrypt(asset.getSecretData()));
        return asset;
    }

    private String typeOrNull(String type) {
        return type == null || type.isBlank() ? null : requireType(type);
    }

    private String textOrNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String requireType(String type) {
        String value = type == null ? "" : type.trim().toUpperCase();
        if (!TYPES.contains(value))
            throw BusinessException.validation("资产类型仅支持个号、BM、像素、TG、主页、电脑、手机、静态 IP、邮箱");
        return value;
    }

    private record BatchAssetUpdate(MediaAsset asset, List<Long> usageUserIds) {}

    /** 仅存在于当前事务内的明文快照；敏感值在生成事件时立即转换为设置状态。 */
    record AssetAuditSnapshot(
            String assetType,
            String assetName,
            String assetCode,
            String channelId,
            String channelName,
            String projectId,
            String projectName,
            String usageTeam,
            String status,
            Long assigneeId,
            String assigneeName,
            String usageUserIds,
            String usageUserNames,
            String remark,
            Map<String, String> details) {}
}
