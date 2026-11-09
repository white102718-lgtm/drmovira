package com.adpulse.main.cloak.service;

import com.adpulse.main.cloak.client.GlobalPwaClient;
import com.adpulse.main.cloak.client.GlobalPwaClient.GlobalPwaClientException;
import com.adpulse.main.cloak.dto.CloakRequests;
import com.adpulse.main.cloak.dto.CloakViews;
import com.adpulse.main.cloak.mapper.CloakMapper;
import com.adpulse.main.cloak.model.CloakBatch;
import com.adpulse.main.cloak.model.CloakRecord;
import com.adpulse.main.project.dto.ProjectViews;
import com.adpulse.main.project.service.ProjectService;
import com.adpulse.main.project.service.ProjectService.ProjectException;
import com.adpulse.system.common.security.CurrentUser;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/** 斗篷配置、批量创建和本地管理列表服务。 */
@Service
public class CloakService {
    private final GlobalPwaClient globalPwaClient;
    private final CloakMapper mapper;
    private final CloakPersistenceService persistenceService;
    private final CloakSheetWritebackService sheetWritebackService;
    private final ProjectService projectService;

    public CloakService(
            GlobalPwaClient globalPwaClient,
            CloakMapper mapper,
            CloakPersistenceService persistenceService,
            CloakSheetWritebackService sheetWritebackService,
            ProjectService projectService) {
        this.globalPwaClient = globalPwaClient;
        this.mapper = mapper;
        this.persistenceService = persistenceService;
        this.sheetWritebackService = sheetWritebackService;
        this.projectService = projectService;
    }

    /** 查询可用推广域名，并过滤服务商返回的无效或重复选项。 */
    public List<CloakViews.DomainOption> listDomains() {
        Map<String, CloakViews.DomainOption> options = new LinkedHashMap<>();
        for (GlobalPwaClient.ProviderDomain domain : globalPwaClient.listDomains()) {
            String genId = normalize(domain.genId());
            String genDomain = normalize(domain.genDomain());
            if (genId == null || genDomain == null) continue;
            String value = normalize(domain.value());
            String label = normalize(domain.label());
            CloakViews.DomainOption option =
                    new CloakViews.DomainOption(
                            genId,
                            genDomain,
                            value == null ? genId : value,
                            label == null ? genDomain : label);
            options.putIfAbsent(option.value(), option);
        }
        return List.copyOf(options.values());
    }

    /** 查询可用投放地区，并过滤服务商返回的无效或重复选项。 */
    public List<CloakViews.CountryOption> listCountries() {
        Map<String, CloakViews.CountryOption> options = new LinkedHashMap<>();
        for (GlobalPwaClient.ProviderCountry country : globalPwaClient.listCountries()) {
            String countryCode = normalize(country.country());
            if (countryCode == null) continue;
            String value = normalize(country.value());
            String label = normalize(country.label());
            CloakViews.CountryOption option =
                    new CloakViews.CountryOption(
                            countryCode,
                            value == null ? countryCode : value,
                            label == null ? countryCode : label);
            options.putIfAbsent(option.value(), option);
        }
        return List.copyOf(options.values());
    }

    /** 查询项目中已经存在于斗篷管理列表、必须先删除后才能重新创建的代理线。 */
    public List<String> listOccupiedAgencyLineIds(String projectId) {
        Long normalizedProjectId = parseId(projectId, "项目ID不合法");
        List<ProjectViews.ProjectAgencyLineDeliveryOption> lines;
        try {
            lines = projectService.listProjectAgencyLineDeliveryOptions(normalizedProjectId);
        } catch (ProjectException exception) {
            throw new CloakException(exception.getMessage());
        }
        if (lines.isEmpty()) return List.of();
        List<Long> lineIds =
                lines.stream().map(line -> parseId(line.id(), "代理线ID不合法")).toList();
        return mapper.findOccupiedAgencyLineIds(lineIds, null).stream()
                .map(String::valueOf)
                .toList();
    }

    /** 批量创建斗篷；真实链接和应用名称均由后端可信项目数据生成。 */
    public CloakViews.BatchResult createBatch(CloakRequests.BatchCreate request) {
        CurrentUser operator = currentUser();
        Long projectId = parseId(request.projectId(), "项目ID不合法");
        ProjectViews.ProjectSearchOption project;
        Map<String, ProjectViews.ProjectAgencyLineDeliveryOption> lines = new LinkedHashMap<>();
        try {
            project = projectService.requireProjectExists(projectId);
            for (ProjectViews.ProjectAgencyLineDeliveryOption line :
                    projectService.listProjectAgencyLineDeliveryOptions(projectId)) {
                lines.put(line.id(), line);
            }
        } catch (ProjectException exception) {
            throw new CloakException(exception.getMessage());
        }

        String reviewUrl = requireReviewUrl(request.reviewUrl());
        int type = providerType(request.mode());
        int langStatus = request.blockedLanguage() ? 0 : 1;
        int pcStatus = request.blockedPc() ? 0 : 1;
        int vpnStatus = request.blockedProxy() ? 0 : 1;
        String country = normalize(request.country());
        String countryLabel = normalize(request.countryLabel());
        List<Long> projectLineIds =
                lines.keySet().stream().map(id -> parseId(id, "代理线ID不合法")).toList();
        Set<String> occupiedLineIds =
                projectLineIds.isEmpty()
                        ? Set.of()
                        : mapper.findOccupiedAgencyLineIds(
                                projectLineIds, request.requestId().trim())
                                .stream()
                                .map(String::valueOf)
                                .collect(Collectors.toSet());
        Set<String> lineIds = new LinkedHashSet<>();
        Set<String> promotionUrls = new LinkedHashSet<>();
        List<CloakRecord> records = new ArrayList<>();
        List<GlobalPwaClient.ProviderCloakCreate> providerItems = new ArrayList<>();

        for (CloakRequests.BatchItem item : request.items()) {
            ProjectViews.ProjectAgencyLineDeliveryOption line = lines.get(item.agencyLineId());
            if (line == null || normalize(line.deliveryUrl()) == null) {
                throw new CloakException("所选代理线不属于当前项目或没有投放链接");
            }
            if (occupiedLineIds.contains(line.id())) {
                throw new CloakException("所选代理线已存在斗篷管理记录，请先在斗篷管理中删除后再创建");
            }
            if (!lineIds.add(line.id())) throw new CloakException("同一代理线不能重复创建斗篷");
            String adUrl = item.adUrl().trim();
            String genId = item.genId().trim();
            String genDomain = item.genDomain().trim();
            String promotionUrl = promotionUrl(adUrl, genDomain);
            if (!promotionUrls.add(promotionUrl)) throw new CloakException("推广链接不能重复");

            CloakRecord record = new CloakRecord();
            record.setProjectId(projectId);
            record.setProjectName(project.name());
            record.setAgencyLineId(parseId(line.id(), "代理线ID不合法"));
            record.setAgencyLineName(line.name());
            record.setName(project.name());
            record.setReallyUrl(requireHttpUrl(line.deliveryUrl(), "代理线投放链接不合法"));
            record.setVirtualUrl(reviewUrl);
            record.setAdUrl(adUrl);
            record.setGenId(genId);
            record.setGenDomain(genDomain);
            record.setPromotionUrl(promotionUrl);
            record.setType(type);
            record.setCountry(country);
            record.setCountryLabel(countryLabel);
            record.setLangStatus(langStatus);
            record.setPcStatus(pcStatus);
            record.setVpnStatus(vpnStatus);
            records.add(record);
            providerItems.add(
                    new GlobalPwaClient.ProviderCloakCreate(
                            record.getName(),
                            record.getReallyUrl(),
                            reviewUrl,
                            adUrl,
                            genId,
                            genDomain,
                            type,
                            country,
                            langStatus,
                            pcStatus,
                            vpnStatus));
        }

        CloakBatch candidate = new CloakBatch();
        candidate.setRequestId(request.requestId().trim());
        candidate.setRequestFingerprint(fingerprint(request, records));
        candidate.setProjectId(projectId);
        candidate.setProjectName(project.name());
        candidate.setTotalCount(records.size());
        CloakPersistenceService.PrepareResult prepared =
                persistenceService.prepare(candidate, records, operator.userId());
        boolean shouldCallProvider = prepared.shouldCallProvider();
        if (prepared.shouldReconcileProvider()) {
            ProviderReconciliation reconciliation = reconcileProviderRecords(records);
            if (reconciliation == ProviderReconciliation.MATCHED) {
                persistenceService.markSuccess(
                        prepared.batch().getId(),
                        records.size(),
                        "服务商对账确认创建成功",
                        operator.userId());
                return new CloakViews.BatchResult(
                        prepared.batch().getId().toString(), records.size(), true);
            }
            if (reconciliation == ProviderReconciliation.CONFLICT) {
                throw new CloakException("服务商存在相同推广链接前缀，但记录参数不一致，请人工核对");
            }
            persistenceService.resetForRetry(prepared.batch().getId(), operator.userId());
            shouldCallProvider = true;
        }
        if (!shouldCallProvider) {
            persistenceService.backfillAgencyLineCloakUrls(
                    prepared.batch().getId(), operator.userId());
            return new CloakViews.BatchResult(
                    prepared.batch().getId().toString(),
                    prepared.batch().getTotalCount(),
                    prepared.reused());
        }

        try {
            String providerMessage = globalPwaClient.createBatch(providerItems);
            persistenceService.markSuccess(
                    prepared.batch().getId(), records.size(), providerMessage, operator.userId());
        } catch (GlobalPwaClientException exception) {
            if (exception.isUncertain() || exception.isDuplicatePromotionUrl()) {
                ProviderReconciliation reconciliation;
                try {
                    reconciliation = reconcileProviderRecords(records);
                } catch (GlobalPwaClientException reconciliationException) {
                    persistenceService.markFailed(
                            prepared.batch().getId(),
                            true,
                            exception.getMessage(),
                            operator.userId());
                    throw exception;
                }
                if (reconciliation == ProviderReconciliation.MATCHED) {
                    persistenceService.markSuccess(
                            prepared.batch().getId(),
                            records.size(),
                            "服务商对账确认创建成功",
                            operator.userId());
                    return new CloakViews.BatchResult(
                            prepared.batch().getId().toString(), records.size(), true);
                }
                if (reconciliation == ProviderReconciliation.CONFLICT) {
                    String message = "服务商存在相同推广链接前缀，但记录参数不一致，请人工核对";
                    persistenceService.markFailed(
                            prepared.batch().getId(), true, message, operator.userId());
                    throw new CloakException(message);
                }
            }
            persistenceService.markFailed(
                    prepared.batch().getId(),
                    false,
                    exception.getMessage(),
                    operator.userId());
            throw exception;
        }
        return new CloakViews.BatchResult(
                prepared.batch().getId().toString(), records.size(), false);
    }

    /** 将指定成功批次的斗篷链接回写到项目代理线Google Sheet。 */
    public CloakViews.SheetWritebackResult writebackSheet(Long batchId) {
        return sheetWritebackService.writeback(batchId);
    }

    /** 将斗篷管理列表选中的本地记录批量回写到各自项目的Google Sheet。 */
    public CloakViews.RecordSheetWritebackResult writebackRecords(List<String> recordIds) {
        return sheetWritebackService.writebackRecords(
                recordIds.stream()
                        .map(id -> parseId(id, "斗篷记录ID不合法"))
                        .toList());
    }

    /** 分页查询已经由服务商确认成功的本地斗篷记录。 */
    public CloakViews.Page<CloakViews.Record> listRecords(
            String keyword,
            String projectId,
            String country,
            String startDate,
            String endDate,
            int page,
            int pageSize) {
        int normalizedPage = Math.max(page, 1);
        int normalizedPageSize = Math.max(1, Math.min(pageSize, 100));
        Long normalizedProjectId =
                normalize(projectId) == null ? null : parseId(projectId, "项目ID不合法");
        List<CloakViews.Record> items =
                mapper.findRecords(
                                normalize(keyword),
                                normalizedProjectId,
                                normalize(country),
                                normalize(startDate),
                                normalize(endDate),
                                (normalizedPage - 1) * normalizedPageSize,
                                normalizedPageSize)
                        .stream()
                        .map(this::view)
                        .toList();
        long total =
                mapper.countRecords(
                        normalize(keyword),
                        normalizedProjectId,
                        normalize(country),
                        normalize(startDate),
                        normalize(endDate));
        return new CloakViews.Page<>(items, total, normalizedPage, normalizedPageSize);
    }

    /** 删除服务商斗篷，并仅在远程删除成功后软删除本地管理记录。 */
    public void deleteRecords(String ids) {
        CurrentUser operator = currentUser();
        List<Long> recordIds = parseRecordIds(ids);
        List<CloakRecord> records = mapper.findRecordsByIds(recordIds);
        if (records.size() != recordIds.size()) {
            throw new CloakException("部分斗篷记录不存在或已删除，请刷新后重试");
        }

        Set<Long> providerIds = new LinkedHashSet<>();
        for (CloakRecord record : records) {
            if (record.getProviderCloakId() != null) {
                providerIds.add(record.getProviderCloakId());
                continue;
            }
            List<GlobalPwaClient.ProviderCloak> matches =
                    globalPwaClient.listCloaksByAdUrl(record.getAdUrl()).stream()
                            .filter(provider -> sameProviderRecord(record, provider))
                            .toList();
            if (matches.size() > 1) {
                throw new CloakException("服务商存在重复斗篷，无法安全定位删除目标");
            }
            if (matches.size() == 1 && matches.getFirst().id() != null) {
                providerIds.add(matches.getFirst().id());
            }
        }

        if (!providerIds.isEmpty()) {
            globalPwaClient.deleteCloaks(List.copyOf(providerIds));
        }
        persistenceService.softDeleteRecords(recordIds, operator.userId());
    }

    private CloakViews.Record view(CloakRecord record) {
        return new CloakViews.Record(
                record.getId().toString(),
                record.getProjectId().toString(),
                record.getProjectName(),
                record.getAgencyLineId().toString(),
                record.getAgencyLineName(),
                record.getReallyUrl(),
                record.getVirtualUrl(),
                record.getPromotionUrl(),
                switch (record.getType()) {
                    case 0 -> "off";
                    case 2 -> "cloak";
                    default -> "all";
                },
                record.getCountry(),
                record.getCountryLabel(),
                record.getLangStatus() == 0,
                record.getPcStatus() == 0,
                record.getVpnStatus() == 0,
                sheetWritebackStatus(record.getSheetWritebackStatus()),
                record.getSheetWritebackMessage(),
                record.getCreatedAt());
    }

    private String sheetWritebackStatus(Integer status) {
        if (Integer.valueOf(1).equals(status)) return "success";
        if (Integer.valueOf(2).equals(status)) return "failed";
        return "pending";
    }

    private boolean sameProviderRecord(
            CloakRecord record, GlobalPwaClient.ProviderCloak provider) {
        return record.getAdUrl().equals(normalize(provider.adUrl()))
                && record.getGenId().equals(normalize(provider.genId()))
                && record.getGenDomain().equals(normalize(provider.genDomain()))
                && record.getReallyUrl().equals(normalize(provider.reallyUrl()));
    }

    private ProviderReconciliation reconcileProviderRecords(List<CloakRecord> records) {
        boolean matched = false;
        boolean absent = false;
        for (CloakRecord record : records) {
            List<GlobalPwaClient.ProviderCloak> sameKeyRecords =
                    globalPwaClient.listCloaksByAdUrl(record.getAdUrl()).stream()
                            .filter(
                                    provider ->
                                            record.getAdUrl().equals(normalize(provider.adUrl()))
                                                    && record.getGenId()
                                                            .equals(normalize(provider.genId())))
                            .toList();
            List<GlobalPwaClient.ProviderCloak> exactMatches =
                    sameKeyRecords.stream()
                            .filter(provider -> sameProviderRecord(record, provider))
                            .toList();
            if (exactMatches.size() == 1) {
                matched = true;
                continue;
            }
            if (!sameKeyRecords.isEmpty()) return ProviderReconciliation.CONFLICT;
            absent = true;
        }
        if (matched && absent) return ProviderReconciliation.CONFLICT;
        return matched ? ProviderReconciliation.MATCHED : ProviderReconciliation.ABSENT;
    }

    private List<Long> parseRecordIds(String value) {
        if (normalize(value) == null) throw new CloakException("请选择要删除的斗篷记录");
        Set<Long> ids = new LinkedHashSet<>();
        for (String part : value.split(",")) {
            ids.add(parseId(part, "斗篷记录ID不合法"));
        }
        if (ids.isEmpty() || ids.size() > 100) {
            throw new CloakException("每次只能删除1至100条斗篷记录");
        }
        return List.copyOf(ids);
    }

    private String fingerprint(CloakRequests.BatchCreate request, List<CloakRecord> records) {
        StringBuilder canonical =
                new StringBuilder()
                        .append(request.projectId().trim())
                        .append('|')
                        .append(request.reviewUrl().trim())
                        .append('|')
                        .append(request.mode())
                        .append('|')
                        .append(normalize(request.country()))
                        .append('|')
                        .append(request.blockedLanguage())
                        .append('|')
                        .append(request.blockedPc())
                        .append('|')
                        .append(request.blockedProxy());
        for (CloakRecord record : records) {
            canonical.append('|')
                    .append(record.getAgencyLineId())
                    .append(':')
                    .append(record.getName())
                    .append(':')
                    .append(record.getReallyUrl())
                    .append(':')
                    .append(record.getAdUrl())
                    .append(':')
                    .append(record.getGenId())
                    .append(':')
                    .append(record.getGenDomain());
        }
        try {
            byte[] digest =
                    MessageDigest.getInstance("SHA-256")
                            .digest(canonical.toString().getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("运行环境不支持SHA-256", exception);
        }
    }

    private int providerType(String mode) {
        return switch (mode) {
            case "off" -> 0;
            case "all" -> 1;
            case "cloak" -> 2;
            default -> throw new CloakException("斗篷模式不合法");
        };
    }

    private String promotionUrl(String adUrl, String genDomain) {
        String suffix = genDomain.startsWith(".") ? genDomain : "." + genDomain;
        return "https://" + adUrl + suffix;
    }

    private String requireHttpUrl(String value, String message) {
        String normalized = normalize(value);
        if (normalized == null) throw new CloakException(message);
        try {
            URI uri = URI.create(normalized);
            if (!("http".equalsIgnoreCase(uri.getScheme())
                    || "https".equalsIgnoreCase(uri.getScheme()))) {
                throw new CloakException(message);
            }
            return normalized;
        } catch (IllegalArgumentException exception) {
            throw new CloakException(message);
        }
    }

    private String requireReviewUrl(String value) {
        String normalized = normalize(value);
        if (normalized != null && normalized.startsWith("/profile/")) return normalized;
        return requireHttpUrl(value, "审核链接必须为HTTP(S)链接或/profile/上传路径");
    }

    private Long parseId(String value, String message) {
        try {
            return Long.valueOf(value.trim());
        } catch (RuntimeException exception) {
            throw new CloakException(message);
        }
    }

    private CurrentUser currentUser() {
        var authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) throw new CloakException("登录状态无效");
        Object principal = authentication.getPrincipal();
        if (principal instanceof CurrentUser user) return user;
        throw new CloakException("登录状态无效");
    }

    private String normalize(String value) {
        if (value == null || value.isBlank()) return null;
        return value.trim();
    }

    private enum ProviderReconciliation {
        MATCHED,
        ABSENT,
        CONFLICT
    }

    /** 可直接展示的斗篷业务异常。 */
    public static class CloakException extends RuntimeException {
        public CloakException(String message) {
            super(message);
        }
    }
}
