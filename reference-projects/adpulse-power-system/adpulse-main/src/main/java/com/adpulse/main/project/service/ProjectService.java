package com.adpulse.main.project.service;

import com.adpulse.main.integration.security.IntegrationSecretCipher;
import com.adpulse.main.project.dto.ProjectRequests;
import com.adpulse.main.project.dto.ProjectRequests.AgencyLinePatch;
import com.adpulse.main.project.dto.ProjectRequests.AgencyLineSave;
import com.adpulse.main.project.dto.ProjectRequests.ProjectSave;
import com.adpulse.main.project.dto.ProjectViews;
import com.adpulse.main.project.dto.ProjectViews.AgencyLineDetail;
import com.adpulse.main.project.dto.ProjectViews.Kpi;
import com.adpulse.main.project.dto.ProjectViews.ProjectDetail;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.AgencyLine;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.model.ProjectOptionRow;
import com.adpulse.main.project.model.ProjectReadRows;
import com.adpulse.main.project.model.ProjectStatisticsRow;
import com.adpulse.main.project.model.ProjectUserAssignment;
import com.adpulse.main.project.model.RegionCountry;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProjectWalletContext;
import com.adpulse.main.project.wallet.ProjectWalletProvider.UserReference;
import com.adpulse.main.project.wallet.ProjectWalletProvisioningService;
import com.adpulse.main.project.wallet.ProjectWalletProvisioningService.ProjectWalletProvisioningException;
import com.adpulse.main.safeheron.service.SafeheronWalletService;
import com.adpulse.main.safeheron.service.SafeheronWalletService.SafeheronWalletException;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.net.URI;
import java.time.LocalDate;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 项目及其代理线的业务服务。 */
@Service
public class ProjectService {
    private static final Logger log = LoggerFactory.getLogger(ProjectService.class);
    private static final int MAX_PROJECT_PAGE_SIZE = 999_999;
    private static final Set<String> TERMINAL_STATUSES = Set.of("ended", "archived");
    private static final Set<String> PROJECT_STATUSES =
            Set.of("pending", "active", "paused", "ended", "archived");
    private static final Set<String> PRIORITIES = Set.of("low", "normal", "high");
    private static final Set<String> PROJECT_TYPES =
            Set.of("game", "app", "ecommerce", "website", "other");
    private static final Set<String> KPI_METRICS = Set.of("CPP", "CPA", "ROAS");
    private static final Set<String> COMPARATORS = Set.of(">", "<", "=", ">=", "<=", "between");
    private final ProjectMapper mapper;
    private final SafeheronWalletService walletService;
    private final ProjectWalletProvisioningService walletProvisioningService;
    private final ProjectSpendQueryProvider spendQueryProvider;
    private final IntegrationSecretCipher cipher;

    /** 任务提交时用于新增或覆盖代理线主数据的字段。 */
    public record DeliveryTaskAgencyLineInput(
            String name,
            String platform,
            String type,
            String pixelName,
            String pixelId,
            String token,
            String testCode,
            String deliveryUrl,
            String cloakUrl,
            String optimizerId) {}

    /** 任务快照需要保存的代理线稳定标识与规范化字段。 */
    public record DeliveryTaskAgencyLineResult(String id, String name, String platform) {}

    @Autowired
    public ProjectService(
            ProjectMapper mapper,
            SafeheronWalletService walletService,
            ProjectWalletProvisioningService walletProvisioningService,
            ProjectSpendQueryProvider spendQueryProvider,
            IntegrationSecretCipher cipher) {
        this.mapper = mapper;
        this.walletService = walletService;
        this.walletProvisioningService = walletProvisioningService;
        this.spendQueryProvider = spendQueryProvider;
        this.cipher = cipher;
    }

    /** 兼容只验证非敏感字段的既有单元测试构造方式。 */
    ProjectService(
            ProjectMapper mapper,
            SafeheronWalletService walletService,
            ProjectSpendQueryProvider spendQueryProvider) {
        this.mapper = mapper;
        this.walletService = walletService;
        this.walletProvisioningService = null;
        this.spendQueryProvider = spendQueryProvider;
        this.cipher = null;
    }

    /** 分页查询项目，不加载代理线；绑定关系在查看详情时查询。 */
    public ProjectViews.Page<ProjectDetail> listProjects(
            String keyword, String status, String platform, int page, int pageSize) {
        int safePage = Math.max(1, page);
        int safeSize = Math.min(MAX_PROJECT_PAGE_SIZE, Math.max(1, pageSize));
        String normalizedStatus = optionalLower(status);
        String normalizedPlatform = optionalLower(platform);
        Long scopeUserId = dataScopeUserId();
        List<Project> projects =
                mapper.findProjects(
                        trimToNull(keyword),
                        normalizedStatus,
                        normalizedPlatform,
                        scopeUserId,
                        (safePage - 1) * safeSize,
                        safeSize);
        List<ProjectDetail> items = listDetails(projects);
        return new ProjectViews.Page<>(
                items,
                mapper.countProjects(
                        trimToNull(keyword), normalizedStatus, normalizedPlatform, scopeUserId),
                safePage,
                safeSize);
    }

    /** 复用列表计数口径，仅统计未删除数据，不加载列表及关联详情。 */
    public ProjectViews.TabCounts getTabCounts() {
        return new ProjectViews.TabCounts(
                mapper.countProjects(null, null, null),
                mapper.countAgencyLines(null, null, null, null, null));
    }

    /** 按名称或编码查询全部项目的轻量选项，不应用项目列表数据范围。 */
    public List<ProjectViews.ProjectSearchOption> searchAllProjectOptions(String keyword) {
        return mapper.findProjectSearchOptions(normalizeProjectOptionKeyword(keyword), null);
    }

    /** 按名称或编码查询当前用户数据范围内的轻量项目选项。 */
    public List<ProjectViews.ProjectSearchOption> searchScopedProjectOptions(String keyword) {
        return mapper.findProjectSearchOptions(
                normalizeProjectOptionKeyword(keyword), dataScopeUserId());
    }

    /** 查询项目关联代理线的轻量投放链接选项；供已获对应功能权限的下游业务选择。 */
    public List<ProjectViews.ProjectAgencyLineDeliveryOption>
            listProjectAgencyLineDeliveryOptions(Long projectId) {
        requireProjectExists(projectId);
        return mapper.findProjectAgencyLineDeliveryOptions(projectId, null, 100);
    }

    /** 返回项目页面统计和轻量项目选项。 */
    public ProjectViews.ProjectContext getProjectContext() {
        ProjectStatisticsRow counts = mapper.countProjectStatuses();
        ProjectViews.ProjectStatistics statistics =
                new ProjectViews.ProjectStatistics(
                        counts.getTotal(),
                        counts.getActive(),
                        counts.getDraftOrPending(),
                        counts.getEndedOrArchived());
        Map<Long, ProjectOptionBuilder> options = new LinkedHashMap<>();
        for (ProjectOptionRow row : mapper.findProjectOptionRows()) {
            ProjectOptionBuilder option =
                    options.computeIfAbsent(
                            row.getId(),
                            ignored ->
                                    new ProjectOptionBuilder(
                                            row.getId(),
                                            row.getProjectName(),
                                            row.getProjectCode(),
                                            row.getStatus()));
            if (row.getPlatformValue() != null) {
                option.platforms.add(row.getPlatformValue());
            }
        }
        return new ProjectViews.ProjectContext(
                statistics, options.values().stream().map(ProjectOptionBuilder::view).toList());
    }

    /** 返回按业务地区分组的国家级联选项。 */
    public List<ProjectViews.RegionOption> listRegionOptions() {
        Map<String, RegionOptionBuilder> regions = new LinkedHashMap<>();
        for (RegionCountry item : mapper.findEnabledRegionCountries()) {
            regions.computeIfAbsent(
                            item.getRegionCode(),
                            ignored ->
                                    new RegionOptionBuilder(
                                            item.getRegionCode(), item.getRegionName()))
                    .countries
                    .add(
                            new ProjectViews.CountryOption(
                                    item.getCountryCode(), item.getCountryName()));
        }
        return regions.values().stream().map(RegionOptionBuilder::view).toList();
    }

    /** 查询项目详情。 */
    public ProjectDetail getProject(Long id) {
        return detail(requireProject(id));
    }

    /**
     * 校验项目是否存在，仅返回下游选择所需的稳定标识与名称，不校验项目管理列表的数据范围。
     *
     * <p>调用方仍需通过自身功能权限控制接口访问；该方法不会加载项目详情、钱包或其他关联数据。
     */
    public ProjectViews.ProjectSearchOption requireProjectExists(Long id) {
        Project project = requireProject(id);
        return new ProjectViews.ProjectSearchOption(
                String.valueOf(project.getId()), project.getProjectName());
    }

    /** 创建项目。 */
    @Transactional
    public ProjectDetail createProject(ProjectSave request) {
        Project project = new Project();
        project.setProjectCode(normalizeProjectCode(request.projectCode()));
        apply(project, request);
        requireUniqueProjectName(project.getProjectName(), null);
        Long operatorId = currentUserId();
        project.setCreatedBy(operatorId);
        project.setUpdatedBy(operatorId);
        try {
            mapper.insertProject(project);
            replaceChildren(project.getId(), request, operatorId);
            if (Boolean.TRUE.equals(request.createWallet())) {
                if (walletProvisioningService == null) {
                    // 兼容既有服务单元测试构造方式；生产实例统一经过可插拔供应层。
                    if (mapper.countEnabledDictionaryValue("PROJECT_CREATE_WALLET", "0") == 0) {
                        walletService.createProjectWallet(
                                project.getProjectCode(), project.getProjectName());
                    }
                } else {
                    try {
                        walletProvisioningService.provision(walletContext(project));
                    } catch (ProjectWalletProvisioningException exception) {
                        // 项目是主数据，外部钱包失败不能回滚已创建项目；详情返回无钱包供用户重试。
                        log.warn(
                                "项目创建成功但钱包关联失败: projectId={}, reason={}",
                                project.getId(),
                                exception.getMessage());
                    }
                }
            }
        } catch (DuplicateKeyException exception) {
            throw new ProjectException("项目编码或名称已存在，请使用其他值");
        } catch (SafeheronWalletException exception) {
            throw new ProjectException(exception.getMessage());
        }
        return getProject(project.getId());
    }

    /** 按当前字典配置为已有项目幂等创建或同步入金币钱包。 */
    @Transactional
    public ProjectViews.ProjectWallet createProjectWallet(Long id) {
        Project project = requireProject(id);
        String walletRef = walletReference(project);
        ProjectViews.ProjectWallet existing = walletService.findProjectWallet(walletRef);
        if (existing != null) return existing;
        try {
            if (walletProvisioningService != null) {
                return walletProvisioningService.provision(walletContext(project));
            }
            return walletService.createProjectWallet(
                    project.getProjectCode(), project.getProjectName());
        } catch (SafeheronWalletException | ProjectWalletProvisioningException exception) {
            throw new ProjectException(exception.getMessage());
        }
    }

    /** 修改非结束、非归档项目；项目媒体平台仅作为展示配置，不约束已绑定代理线。 */
    @Transactional
    public ProjectDetail updateProject(Long id, ProjectSave request) {
        Project project = requireMutableProject(id);
        apply(project, request);
        requireUniqueProjectName(project.getProjectName(), id);
        project.setUpdatedBy(currentUserId());
        try {
            mapper.updateProject(project);
        } catch (DuplicateKeyException exception) {
            throw new ProjectException("项目名称已存在，请使用其他名称");
        }
        replaceChildren(id, request, project.getUpdatedBy());
        return getProject(id);
    }

    /** 增量绑定或解绑代理线。 */
    @Transactional
    public ProjectDetail patchAgencyLines(Long projectId, AgencyLinePatch request) {
        Project project = requireMutableProject(projectId);
        Set<Long> add = parseIds(request.add());
        Set<Long> remove = parseIds(request.remove());
        if (add.stream().anyMatch(remove::contains)) {
            throw new ProjectException("同一代理线不能同时绑定和解绑");
        }
        Long operatorId = currentUserId();
        for (Long lineId : remove) {
            requireAgencyLine(lineId);
            mapper.unbindAgencyLine(lineId, projectId, operatorId);
        }
        for (Long lineId : add) {
            bind(project, requireAgencyLine(lineId), operatorId);
        }
        return getProject(projectId);
    }

    /** 使用代理线ID集合覆盖项目当前绑定。 */
    @Transactional
    public ProjectDetail replaceAgencyLines(Long projectId, List<String> lineIds) {
        Project project = requireMutableProject(projectId);
        Set<Long> requested = parseIds(lineIds);
        Long operatorId = currentUserId();
        for (AgencyLine current :
                mapper.findAgencyLines(
                        null, null, null, projectId, null, null, 0, Integer.MAX_VALUE)) {
            if (!requested.contains(current.getId())) {
                mapper.unbindAgencyLine(current.getId(), projectId, operatorId);
            }
        }
        for (Long lineId : requested) {
            bind(project, requireAgencyLine(lineId), operatorId);
        }
        return getProject(projectId);
    }

    /** 结项金额按币种汇总；项目任务摘要独立于个人任务中心的参与者范围。 */
    public ProjectViews.OperatingOverview operatingOverview(Long id) {
        currentUserId();
        ProjectDetail project = getProject(id);
        List<ProjectViews.SettledAmount> settledAmounts =
                summarizeSettlements(mapper.findClosureSettlements(id));
        return new ProjectViews.OperatingOverview(
                project,
                spendQueryProvider.totalSpend(project.name()),
                settledAmounts.stream()
                        .filter(value -> "USD".equals(value.currency()))
                        .map(ProjectViews.SettledAmount::amount)
                        .findFirst()
                        .orElse(BigDecimal.ZERO),
                "USD",
                "unsettled",
                false,
                "",
                0,
                List.of(),
                mapper.countProjectTasks(id, true),
                mapper.findCompletedProjectTasks(id, 0, 10),
                0,
                mapper.countProjectTasks(id, false),
                "complete",
                "累计消耗按项目名称汇总全部历史广告系列层级消耗（USD）；服务费暂未接入；已结算按已办理完成的项目结项记录分币种汇总，不代表实际到账。",
                settledAmounts);
    }

    /** 金额使用十进制定点累加；异常历史字段明确报错，不静默漏算或归入美元。 */
    static List<ProjectViews.SettledAmount> summarizeSettlements(
            List<ProjectViews.ClosureSettlement> records) {
        Map<String, BigDecimal> totals = new java.util.TreeMap<>();
        for (var record : records) {
            String currency =
                    record.currency() == null
                            ? ""
                            : record.currency().trim().toUpperCase(Locale.ROOT);
            currency = currency.split("\\s+-\\s+", 2)[0];
            if (!Set.of("USD", "CNY", "JPY").contains(currency)) {
                throw new ProjectException("结项记录币种缺失或不支持，请检查结项记录");
            }
            try {
                BigDecimal amount = new BigDecimal(record.amount().trim());
                if (amount.signum() < 0) throw new NumberFormatException();
                totals.merge(currency, amount, BigDecimal::add);
            } catch (NumberFormatException | NullPointerException ex) {
                throw new ProjectException("结项记录金额无效，请检查结项记录");
            }
        }
        return totals.entrySet().stream()
                .map(entry -> new ProjectViews.SettledAmount(entry.getKey(), entry.getValue()))
                .toList();
    }

    /** 分页读取项目全部已完成投放、素材任务摘要，不开放原任务详情权限。 */
    public ProjectViews.Page<ProjectViews.CompletedTask> completedTasks(
            Long id, int page, int pageSize) {
        currentUserId();
        requireProject(id);
        int safePage = Math.max(1, page);
        int safeSize = Math.min(100, Math.max(1, pageSize));
        return new ProjectViews.Page<>(
                mapper.findCompletedProjectTasks(
                        id, Math.toIntExact((long) (safePage - 1) * safeSize), safeSize),
                mapper.countProjectTasks(id, true),
                safePage,
                safeSize);
    }

    /** 仅修改项目内代理线业务状态，不调用媒体平台；结束或归档项目禁止操作。 */
    @Transactional
    public void changeAgencyLineStatus(
            Long projectId, ProjectRequests.AgencyLineStatusChange request) {
        Long operatorId = currentUserId();
        requireMutableProject(projectId);
        if (!Set.of("active", "stopped")
                .contains(request.status() == null ? "" : request.status())) {
            throw new ProjectException("代理线状态不合法");
        }
        if (request.agencyLineIds() == null
                || request.agencyLineIds().isEmpty()
                || request.agencyLineIds().size() > 100) {
            throw new ProjectException("每次请选择1至100条代理线");
        }
        // 先校验整批归属，后更新；写入时再次限制项目，避免并发解绑后误改其他项目。
        List<Long> ids = parseIds(request.agencyLineIds()).stream().sorted().toList();
        for (Long id : ids) {
            if (!projectId.equals(requireAgencyLine(id).getProjectId())) {
                throw new ProjectException("所选代理线不属于当前项目");
            }
        }
        for (Long id : ids) {
            if (mapper.updateAgencyLineStatus(id, projectId, request.status(), operatorId) != 1) {
                throw new ProjectException("代理线归属已变化，请刷新后重试");
            }
        }
    }

    /** 批量修改代理线业务状态，先验证全批可修改性，再在同一事务中更新。 */
    @Transactional
    public void changeAgencyLineStatuses(ProjectRequests.AgencyLineStatusChange request) {
        if (!Set.of("active", "stopped").contains(request.status() == null ? "" : request.status()))
            throw new ProjectException("代理线状态不合法");
        if (request.agencyLineIds() == null
                || request.agencyLineIds().isEmpty()
                || request.agencyLineIds().size() > 100)
            throw new ProjectException("每次请选择1至100条代理线");
        Long operatorId = currentUserId();
        List<AgencyLine> lines =
                parseIds(request.agencyLineIds()).stream()
                        .sorted()
                        .map(this::requireAgencyLine)
                        .toList();
        for (AgencyLine line : lines) requireLineMutable(line);
        for (AgencyLine line : lines) {
            if (mapper.updateAgencyLineStatus(
                            line.getId(), line.getProjectId(), request.status(), operatorId)
                    != 1) throw new ProjectException("代理线归属或项目状态已变化，请刷新后重试");
        }
    }

    /** 选择人员后即时更新归属，姓名由人员表决定，不接受客户端自定义。 */
    @Transactional
    public AgencyLineDetail changeAgencyLineOptimizer(
            Long id, ProjectRequests.AgencyLineOptimizerChange request) {
        AgencyLine line = requireAgencyLine(id);
        requireLineMutable(line);
        applyOptimizer(line, request.optimizerId(), null);
        line.setUpdatedBy(currentUserId());
        if (mapper.updateAgencyLineOptimizer(line) != 1)
            throw new ProjectException("代理线归属或项目状态已变化，请刷新后重试");
        return getAgencyLine(id);
    }

    /** 按名称搜索未绑定项目的代理线，限制结果数量以供下拉选择。 */
    public List<ProjectViews.AgencyLineOption> listUnboundAgencyLineOptions(String keyword) {
        return mapper.findUnboundAgencyLineOptions(trimToNull(keyword));
    }

    /** 分页查询代理线。 */
    public ProjectViews.Page<AgencyLineDetail> listAgencyLines(
            String keyword,
            String lineName,
            String platform,
            Long projectId,
            Long optimizerId,
            int page,
            int pageSize) {
        int safePage = Math.max(1, page);
        int safeSize = Math.min(1000, Math.max(1, pageSize));
        String normalizedPlatform = optionalLower(platform);
        List<String> keywords = normalizeAgencyLineKeywords(keyword);
        Long scopeUserId = dataScopeUserId();
        List<AgencyLineDetail> items =
                mapper
                        .findAgencyLines(
                                keywords,
                                trimToNull(lineName),
                                normalizedPlatform,
                                projectId,
                                optimizerId,
                                scopeUserId,
                                (safePage - 1) * safeSize,
                                safeSize)
                        .stream()
                        .map(this::detail)
                        .toList();
        return new ProjectViews.Page<>(
                items,
                mapper.countAgencyLines(
                        keywords,
                        trimToNull(lineName),
                        normalizedPlatform,
                        projectId,
                        optimizerId,
                        scopeUserId),
                safePage,
                safeSize);
    }

    /** 将多行关键词规范化为 OR 查询条件，限制数量和长度以控制动态 SQL 规模。 */
    private List<String> normalizeAgencyLineKeywords(String keyword) {
        if (keyword == null || keyword.isBlank()) return List.of();
        List<String> keywords =
                keyword.lines()
                        .map(String::trim)
                        .filter(value -> !value.isEmpty())
                        .distinct()
                        .toList();
        if (keywords.size() > 100) throw new ProjectException("关键词最多输入100行");
        if (keywords.stream().anyMatch(value -> value.length() > 1000)) {
            throw new ProjectException("单行关键词不能超过1000个字符");
        }
        return keywords;
    }

    /** 查询单条代理线。 */
    public AgencyLineDetail getAgencyLine(Long id) {
        return detail(requireAgencyLine(id));
    }

    /** 创建代理线并可选绑定一个项目。 */
    @Transactional
    public AgencyLineDetail createAgencyLine(
            AgencyLineSave request, String wrapperProjectId, String requestId) {
        String normalizedRequestId = trimToNull(requestId);
        if (normalizedRequestId != null) {
            AgencyLine existing = mapper.findAgencyLineByRequestId(normalizedRequestId);
            if (existing != null) {
                return detail(existing);
            }
        }
        AgencyLine line = new AgencyLine();
        apply(line, request, wrapperProjectId);
        line.setRequestId(normalizedRequestId);
        Long operatorId = currentUserId();
        line.setCreatedBy(operatorId);
        line.setUpdatedBy(operatorId);
        try {
            mapper.insertAgencyLine(line);
        } catch (DuplicateKeyException exception) {
            AgencyLine existing =
                    normalizedRequestId == null
                            ? null
                            : mapper.findAgencyLineByRequestId(normalizedRequestId);
            if (existing != null) {
                return detail(existing);
            }
            throw new ProjectException("代理线名称已存在，请使用其他名称");
        }
        recordDeliveryUrlVersion(line, operatorId);
        return getAgencyLine(line.getId());
    }

    /** 修改代理线；所属项目结束或归档后禁止修改。 */
    @Transactional
    public AgencyLineDetail updateAgencyLine(Long id, AgencyLineSave request) {
        AgencyLine line = requireAgencyLine(id);
        requireLineMutable(line);
        String previousDeliveryUrl = trimToNull(line.getDeliveryUrl());
        apply(line, request, request.projectId());
        Long operatorId = currentUserId();
        line.setUpdatedBy(operatorId);
        try {
            mapper.updateAgencyLine(line);
        } catch (DuplicateKeyException exception) {
            throw new ProjectException("代理线名称已存在，请使用其他名称");
        }
        if (!Objects.equals(previousDeliveryUrl, line.getDeliveryUrl())) {
            recordDeliveryUrlVersion(line, operatorId);
        }
        return getAgencyLine(id);
    }

    /** 查询代理线投放链接历史；当前链接也包含在版本序列中。 */
    public List<ProjectViews.AgencyLineDeliveryUrlHistory> getAgencyLineDeliveryUrlHistory(Long id) {
        requireAgencyLine(id);
        return mapper.findAgencyLineDeliveryUrlHistory(id);
    }

    /**
     * 正式提交任务时按代理线名称静默新增或覆盖主数据。
     *
     * <p>项目媒体平台仅用于展示，不限制代理线平台。未绑定代理线会绑定当前项目；
     * 已属于其他项目的同名代理线拒绝覆盖，整批由外层事务回滚。
     */
    @Transactional
    public List<DeliveryTaskAgencyLineResult> syncDeliveryTaskAgencyLines(
            Long projectId, List<DeliveryTaskAgencyLineInput> inputs) {
        requireMutableProject(projectId);
        Set<String> lineNames = new LinkedHashSet<>();
        List<DeliveryTaskAgencyLineResult> results = new java.util.ArrayList<>();
        Long operatorId = currentUserId();
        for (DeliveryTaskAgencyLineInput input : inputs) {
            String lineName = requiredText(input.name(), "代理线");
            String nameKey = lineName.toLowerCase(Locale.ROOT);
            if (!lineNames.add(nameKey)) throw new ProjectException("同一任务中代理线不能重复：" + lineName);
            String platform = lower(input.platform());
            requireDictionaryValue("AD_MEDIA", platform);

            AgencyLine line = mapper.findAgencyLineByNameForUpdate(lineName);
            if (line != null
                    && line.getProjectId() != null
                    && !projectId.equals(line.getProjectId())) {
                throw new ProjectException("该代理线已属于其他项目");
            }
            boolean creating = line == null;
            if (creating) line = new AgencyLine();
            String previousDeliveryUrl = creating ? null : trimToNull(line.getDeliveryUrl());
            applyDeliveryTaskAgencyLine(line, projectId, platform, input);
            line.setUpdatedBy(operatorId);
            if (creating) {
                line.setCreatedBy(operatorId);
                try {
                    mapper.insertAgencyLine(line);
                } catch (DuplicateKeyException exception) {
                    throw new ProjectException("代理线数据已发生变化，请重新提交：" + lineName);
                }
                recordDeliveryUrlVersion(line, operatorId);
            } else {
                mapper.updateAgencyLine(line);
                if (!Objects.equals(previousDeliveryUrl, line.getDeliveryUrl())) {
                    recordDeliveryUrlVersion(line, operatorId);
                }
            }
            results.add(
                    new DeliveryTaskAgencyLineResult(
                            line.getId().toString(), line.getLineName(), line.getPlatformValue()));
        }
        return results;
    }

    /** 软删除代理线。 */
    @Transactional
    public void deleteAgencyLine(Long id) {
        AgencyLine line = requireAgencyLine(id);
        requireLineMutable(line);
        mapper.softDeleteAgencyLine(id, System.currentTimeMillis(), currentUserId());
    }

    private void apply(Project project, ProjectSave request) {
        List<ProjectRequests.UserAssignmentSave> amUsers =
                projectUsers(request.amUsers(), request.amUserId(), request.amName(), "AM", true);
        List<ProjectRequests.UserAssignmentSave> specialists =
                projectUsers(
                        request.dataSpecialists(),
                        request.dataSpecialistId(),
                        request.dataSpecialist(),
                        "数据专员",
                        false);
        validateUserPair(request.deliveryLeaderId(), request.deliveryLeaderName(), "投放负责人");
        if (request.dataSpecialists() == null) {
            validateUserPair(request.dataSpecialistId(), request.dataSpecialist(), "数据专员");
        }
        String status = lower(request.status());
        if (!PROJECT_STATUSES.contains(status)) {
            throw new ProjectException("项目状态不合法");
        }
        String priority = lower(request.priority());
        if (!PRIORITIES.contains(priority)) {
            throw new ProjectException("项目优先级不合法");
        }
        String projectType = lower(request.projectType());
        if (!PROJECT_TYPES.contains(projectType)) {
            throw new ProjectException("项目类型不合法");
        }
        validateKpis(request.kpiRequirements());
        request.platforms().forEach(value -> requireDictionaryValue("AD_MEDIA", value));
        request.countryRegions().forEach(this::requireRegionCountry);
        project.setProjectName(request.name().trim());
        project.setProjectType(projectType);
        project.setResponsibleTeam(request.responsibleTeam().trim());
        project.setAmUserId(requiredId(amUsers.getFirst().userId(), "AM用户ID"));
        project.setAmName(amUsers.getFirst().userName().trim());
        project.setDeliveryLeaderId(optionalId(request.deliveryLeaderId(), "投放负责人ID"));
        project.setDeliveryLeaderName(trimToNull(request.deliveryLeaderName()));
        project.setDataSpecialistId(
                specialists.isEmpty()
                        ? null
                        : requiredId(specialists.getFirst().userId(), "数据专员ID"));
        project.setDataSpecialist(
                specialists.isEmpty() ? null : specialists.getFirst().userName().trim());
        project.setOutsourced(request.isOutsourced());
        if (request.isOutsourced() && distinctTrimmed(request.outsourcingTeams()).isEmpty()) {
            throw new ProjectException("有外包项目必须至少选择一个外包团队");
        }
        project.setPriority(priority);
        project.setServiceFeePercent(request.serviceFeePercent());
        project.setStatus(status);
        // 产品信息是原文，空白校验由请求约束承担，保存时不裁剪空白或换行。
        project.setProductInfo(request.productInfo());
        project.setCustomerDailyReportUrl(validateUrl(request.customerDailyReportUrl()));
        project.setAgencyLineUrl(validateUrl(request.agencyLineUrl()));
    }

    private void requireUniqueProjectName(String projectName, Long excludedId) {
        if (mapper.countActiveProjectName(projectName, excludedId) > 0) {
            throw new ProjectException("项目名称已存在，请使用其他名称");
        }
    }

    private void apply(AgencyLine line, AgencyLineSave request, String wrapperProjectId) {
        Long projectId = optionalId(firstNonBlank(request.projectId(), wrapperProjectId), "项目ID");
        if (projectId != null) requireMutableProject(projectId);
        String platform = lower(request.platform());
        requireDictionaryValue("AD_MEDIA", platform);
        applyOptimizer(line, request);
        line.setProjectId(projectId);
        line.setLineName(request.name().trim());
        line.setPlatformValue(platform);
        line.setType(trimToNull(request.type()));
        line.setDeliveryUrl(validateUrl(request.deliveryUrl()));
        line.setPageId(trimToNull(request.pageId()));
        line.setPixelName(trimToNull(request.pixelName()));
        line.setPixelId(trimToNull(request.pixelId()));
        if (request.token() != null) {
            String token = trimToNull(request.token());
            line.setTokenCiphertext(token == null ? null : requireCipher().encrypt(token));
        }
        line.setTestCode(trimToNull(request.testCode()));
        line.setCloakUrl(validateUrl(request.cloakUrl()));
    }

    private void applyDeliveryTaskAgencyLine(
            AgencyLine line,
            Long projectId,
            String platform,
            DeliveryTaskAgencyLineInput input) {
        Long optimizerId = requiredId(input.optimizerId(), "投手ID");
        var optimizer = mapper.findUserReference(optimizerId);
        if (optimizer == null) throw new ProjectException("投手不存在或已删除");
        String token = requiredText(input.token(), "Token");
        line.setProjectId(projectId);
        line.setLineName(requiredText(input.name(), "代理线"));
        line.setPlatformValue(platform);
        line.setType(trimToNull(input.type()));
        line.setPixelName(trimToNull(input.pixelName()));
        line.setPixelId(requiredText(input.pixelId(), "像素ID"));
        line.setTokenCiphertext(requireCipher().encrypt(token));
        line.setTestCode(requiredText(input.testCode(), "测试代码"));
        line.setDeliveryUrl(validateUrl(requiredText(input.deliveryUrl(), "投放链接")));
        line.setCloakUrl(validateUrl(input.cloakUrl()));
        line.setOptimizerId(optimizerId);
        line.setOptimizerName(optimizer.displayName());
        line.setOptimizerStatus(optimizer.status());
    }

    /** 仅在链接实际变化时追加不可变版本；不把相同值的重复保存写入历史。 */
    private void recordDeliveryUrlVersion(AgencyLine line, Long operatorId) {
        int versionNo = Math.max(1, mapper.nextAgencyLineDeliveryUrlVersion(line.getId()));
        if (line.getDeliveryUrl() == null && versionNo == 1) return;
        CurrentUser operator = currentUser();
        mapper.insertAgencyLineDeliveryUrlHistory(
                line.getId(),
                versionNo,
                line.getDeliveryUrl(),
                operatorId,
                operator.displayName());
    }

    /** 全量保存允许清空；停用人员仅能保留数据库中已有的归属。 */
    private void applyOptimizer(AgencyLine line, AgencyLineSave request) {
        applyOptimizer(line, request.optimizerId(), request.optimizerName());
    }

    private void applyOptimizer(AgencyLine line, String rawOptimizerId, String optimizerName) {
        Long optimizerId = optionalId(rawOptimizerId, "优化师ID");
        if (optimizerId != null && optimizerId <= 0) throw new ProjectException("优化师ID必须为正数");
        String name = trimToNull(optimizerName);
        if (optimizerId == null) {
            if (name != null) throw new ProjectException("优化师姓名不能缺少用户ID");
            line.setOptimizerId(null);
            line.setOptimizerName(null);
            line.setOptimizerStatus(null);
            return;
        }
        var user = mapper.findUserReference(optimizerId);
        boolean unchanged = line.getId() != null && optimizerId.equals(line.getOptimizerId());
        if (user == null || (!Integer.valueOf(1).equals(user.status()) && !unchanged)) {
            throw new ProjectException("优化师不存在、已删除或不可新分配停用人员");
        }
        if (name == null && unchanged) name = trimToNull(line.getOptimizerName());
        if (name == null) name = user.displayName();
        line.setOptimizerId(optimizerId);
        line.setOptimizerName(name);
        line.setOptimizerStatus(user.status());
    }

    private void replaceChildren(Long id, ProjectSave request, Long operatorId) {
        long deletedAt = System.currentTimeMillis();
        mapper.softDeletePlatforms(id, deletedAt);
        mapper.softDeleteRegions(id, deletedAt);
        mapper.softDeleteKpis(id, deletedAt, operatorId);
        mapper.softDeleteProductLinks(id, deletedAt);
        mapper.softDeleteOutsourcingTeams(id, deletedAt);
        mapper.softDeleteProjectAms(id, deletedAt);
        mapper.softDeleteProjectDataSpecialists(id, deletedAt);
        distinctLower(request.platforms())
                .forEach(value -> mapper.insertPlatform(id, value, operatorId));
        distinctUpper(request.countryRegions())
                .forEach(
                        countryCode ->
                                mapper.insertRegion(
                                        id, requireRegionCountry(countryCode), operatorId));
        for (int index = 0; index < request.kpiRequirements().size(); index++) {
            ProjectRequests.KpiSave kpi = request.kpiRequirements().get(index);
            mapper.insertKpi(
                    id,
                    kpi.metric().trim().toUpperCase(Locale.ROOT),
                    kpi.comparator(),
                    kpi.target(),
                    kpi.targetMax(),
                    index,
                    operatorId);
        }
        List<String> productLinks =
                request.productLinks().stream().map(this::validateUrl).distinct().toList();
        for (int index = 0; index < productLinks.size(); index++) {
            mapper.insertProductLink(id, productLinks.get(index), index, operatorId);
        }
        if (request.isOutsourced()) {
            distinctTrimmed(request.outsourcingTeams())
                    .forEach(teamName -> mapper.insertOutsourcingTeam(id, teamName, operatorId));
        }
        List<ProjectRequests.UserAssignmentSave> amUsers =
                projectUsers(request.amUsers(), request.amUserId(), request.amName(), "AM", true);
        for (int index = 0; index < amUsers.size(); index++) {
            var user = amUsers.get(index);
            mapper.insertProjectAm(
                    id,
                    requiredId(user.userId(), "AM用户ID"),
                    user.userName().trim(),
                    index,
                    operatorId);
        }
        List<ProjectRequests.UserAssignmentSave> specialists =
                projectUsers(
                        request.dataSpecialists(),
                        request.dataSpecialistId(),
                        request.dataSpecialist(),
                        "数据专员",
                        false);
        for (int index = 0; index < specialists.size(); index++) {
            var user = specialists.get(index);
            mapper.insertProjectDataSpecialist(
                    id,
                    requiredId(user.userId(), "数据专员ID"),
                    user.userName().trim(),
                    index,
                    operatorId);
        }
    }

    /** 校验项目 KPI 的指标唯一性、比较方式以及闭区间边界。 */
    private void validateKpis(List<ProjectRequests.KpiSave> kpis) {
        if (kpis.size() > KPI_METRICS.size()) {
            throw new ProjectException("KPI要求最多配置三项");
        }
        Set<String> metrics = new HashSet<>();
        for (ProjectRequests.KpiSave kpi : kpis) {
            String metric = kpi.metric().trim().toUpperCase(Locale.ROOT);
            if (!KPI_METRICS.contains(metric)) {
                throw new ProjectException("KPI指标不合法：" + kpi.metric());
            }
            if (!metrics.add(metric)) {
                throw new ProjectException("每个KPI指标只能配置一次");
            }
            if (!COMPARATORS.contains(kpi.comparator())) {
                throw new ProjectException("KPI比较符不合法");
            }
            if ("between".equals(kpi.comparator())) {
                if (kpi.targetMax() == null || kpi.target().compareTo(kpi.targetMax()) >= 0) {
                    throw new ProjectException("KPI区间下限必须小于上限");
                }
            } else if (kpi.targetMax() != null) {
                throw new ProjectException("非区间KPI不能设置上限值");
            }
        }
    }

    private void bind(Project project, AgencyLine line, Long operatorId) {
        if (line.getProjectId() != null && !line.getProjectId().equals(project.getId())) {
            throw new ProjectException("代理线“" + line.getLineName() + "”已关联其他项目");
        }
        if (mapper.bindAgencyLine(line.getId(), project.getId(), operatorId) != 1) {
            throw new ProjectException("代理线绑定状态已变化，请刷新后重试");
        }
    }

    /** 仅批量读取当前页关联，查询次数不随每页项目数增长。 */
    private List<ProjectDetail> listDetails(List<Project> projects) {
        if (projects.isEmpty()) return List.of();
        List<Long> ids = projects.stream().map(Project::getId).toList();
        var platforms = valuesByProject(mapper.findPlatformsByProjectIds(ids));
        var regions = valuesByProject(mapper.findRegionsByProjectIds(ids));
        var links = valuesByProject(mapper.findProductLinksByProjectIds(ids));
        var teams = valuesByProject(mapper.findOutsourcingTeamsByProjectIds(ids));
        var kpis =
                groupRows(
                        mapper.findKpisByProjectIds(ids),
                        ProjectReadRows.Kpi::projectId,
                        row ->
                                new Kpi(
                                        row.metric(),
                                        row.comparator(),
                                        row.target(),
                                        row.targetMax()));
        var ams =
                groupRows(
                        mapper.findProjectAmsByProjectIds(ids),
                        ProjectReadRows.User::projectId,
                        row ->
                                new ProjectViews.UserAssignment(
                                        string(row.userId()), row.userName()));
        var specialists =
                groupRows(
                        mapper.findProjectDataSpecialistsByProjectIds(ids),
                        ProjectReadRows.User::projectId,
                        row ->
                                new ProjectViews.UserAssignment(
                                        string(row.userId()), row.userName()));
        var wallets =
                walletService.findProjectWallets(
                        projects.stream().map(this::walletReference).toList());
        return projects.stream()
                .map(
                        project ->
                                detail(
                                        project,
                                        List.of(),
                                        kpis.getOrDefault(project.getId(), List.of()),
                                        links.getOrDefault(project.getId(), List.of()),
                                        teams.getOrDefault(project.getId(), List.of()),
                                        platforms.getOrDefault(project.getId(), List.of()),
                                        regions.getOrDefault(project.getId(), List.of()),
                                        usersOrLegacy(
                                                ams.get(project.getId()),
                                                project.getAmUserId(),
                                                project.getAmName()),
                                        usersOrLegacy(
                                                specialists.get(project.getId()),
                                                project.getDataSpecialistId(),
                                                project.getDataSpecialist()),
                                        wallets.get(walletReference(project))))
                .toList();
    }

    private Map<Long, List<String>> valuesByProject(List<ProjectReadRows.Value> rows) {
        return groupRows(rows, ProjectReadRows.Value::projectId, ProjectReadRows.Value::value);
    }

    private <R, V> Map<Long, List<V>> groupRows(
            List<R> rows, Function<R, Long> projectId, Function<R, V> value) {
        return rows.stream()
                .collect(
                        Collectors.groupingBy(
                                projectId, Collectors.mapping(value, Collectors.toList())));
    }

    private List<ProjectViews.UserAssignment> usersOrLegacy(
            List<ProjectViews.UserAssignment> users, Long legacyId, String legacyName) {
        if (users != null && !users.isEmpty()) return users;
        return legacyId == null
                ? List.of()
                : List.of(new ProjectViews.UserAssignment(string(legacyId), legacyName));
    }

    private ProjectDetail detail(Project project) {
        return detail(
                project,
                mapper.findAgencyLines(
                        null, null, null, project.getId(), null, null, 0, Integer.MAX_VALUE),
                mapper.findKpis(project.getId()),
                mapper.findProductLinks(project.getId()),
                mapper.findOutsourcingTeams(project.getId()),
                mapper.findPlatforms(project.getId()),
                mapper.findRegions(project.getId()),
                userViews(
                        mapper.findProjectAms(project.getId()),
                        project.getAmUserId(),
                        project.getAmName()),
                userViews(
                        mapper.findProjectDataSpecialists(project.getId()),
                        project.getDataSpecialistId(),
                        project.getDataSpecialist()),
                walletService.findProjectWallet(walletReference(project)));
    }

    private ProjectDetail detail(
            Project project,
            List<AgencyLine> lines,
            List<Kpi> kpis,
            List<String> productLinks,
            List<String> outsourcingTeams,
            List<String> platforms,
            List<String> regions,
            List<ProjectViews.UserAssignment> ams,
            List<ProjectViews.UserAssignment> dataSpecialists,
            ProjectViews.ProjectWallet wallet) {
        String productName =
                project.getProductInfo().length() > 80
                        ? project.getProductInfo().substring(0, 80)
                        : project.getProductInfo();
        return new ProjectDetail(
                project.getId().toString(),
                project.getProjectCode(),
                project.getProjectName(),
                project.getProjectType(),
                productLinks,
                productName,
                project.getProductInfo(),
                project.getResponsibleTeam(),
                string(project.getAmUserId()),
                project.getAmName(),
                string(project.getDeliveryLeaderId()),
                project.getDeliveryLeaderName(),
                Boolean.TRUE.equals(project.getOutsourced()),
                outsourcingTeams,
                project.getPriority(),
                platforms,
                regions,
                project.getServiceFeePercent(),
                project.getStatus(),
                project.getCustomerDailyReportUrl(),
                project.getAgencyLineUrl(),
                kpis,
                kpis.isEmpty() ? "" : kpis.getFirst().metric(),
                lines.stream().map(line -> line.getId().toString()).toList(),
                lines.stream().map(AgencyLine::getLineName).toList(),
                List.of(),
                0,
                0,
                BigDecimal.ZERO,
                "USD",
                "",
                "UTC+8",
                LocalDate.now().toString(),
                List.of(),
                project.getDataSpecialist(),
                string(project.getDataSpecialistId()),
                ams,
                dataSpecialists,
                wallet != null,
                wallet,
                project.getUpdatedAt());
    }

    private List<ProjectRequests.UserAssignmentSave> projectUsers(
            List<ProjectRequests.UserAssignmentSave> users,
            String legacyId,
            String legacyName,
            String label,
            boolean required) {
        List<ProjectRequests.UserAssignmentSave> values = users == null ? List.of() : users;
        if (users == null && legacyId != null && !legacyId.isBlank()) {
            values = List.of(new ProjectRequests.UserAssignmentSave(legacyId, legacyName));
        }
        if (required && values.isEmpty()) throw new ProjectException(label + "至少选择一名用户");
        Set<Long> ids = new HashSet<>();
        for (var user : values) {
            if (user.userName() == null || user.userName().isBlank()) {
                throw new ProjectException(label + "必须同时保存用户ID和姓名");
            }
            Long id = requiredId(user.userId(), label + "用户ID");
            if (!ids.add(id)) throw new ProjectException(label + "不能重复选择同一用户");
            if (mapper.countActiveUser(id) != 1) throw new ProjectException(label + "用户不存在或已停用");
        }
        return values;
    }

    private List<ProjectViews.UserAssignment> userViews(
            List<ProjectUserAssignment> users, Long legacyId, String legacyName) {
        if ((users == null || users.isEmpty()) && legacyId != null) {
            return List.of(new ProjectViews.UserAssignment(legacyId.toString(), legacyName));
        }
        if (users == null) return List.of();
        return users.stream()
                .map(
                        user ->
                                new ProjectViews.UserAssignment(
                                        user.getUserId().toString(), user.getUserName()))
                .toList();
    }

    private AgencyLineDetail detail(AgencyLine line) {
        return new AgencyLineDetail(
                line.getId().toString(),
                string(line.getProjectId()),
                line.getLineName(),
                line.getPlatformValue(),
                line.getType() == null ? "" : line.getType(),
                line.getDeliveryUrl() == null ? "" : line.getDeliveryUrl(),
                line.getPixelName(),
                line.getPixelId() == null ? "" : line.getPixelId(),
                decryptToken(line.getTokenCiphertext()),
                line.getTestCode() == null ? "" : line.getTestCode(),
                line.getCloakUrl() == null ? "" : line.getCloakUrl(),
                string(line.getOptimizerId()),
                line.getOptimizerName(),
                line.getOptimizerStatus(),
                line.getStatus() == null ? "active" : line.getStatus(),
                true,
                false,
                false,
                "",
                "",
                "",
                line.getPageId() == null ? "" : line.getPageId(),
                line.getCreatedAt(),
                line.getUpdatedAt());
    }

    private ProjectWalletContext walletContext(Project project) {
        return new ProjectWalletContext(
                project.getId(),
                project.getProjectCode(),
                project.getProjectName(),
                project.getResponsibleTeam(),
                mapper.findRegions(project.getId()).stream()
                        .map(this::requireRegionCountry)
                        .map(RegionCountry::getCountryName)
                        .toList(),
                walletUsers(
                        mapper.findProjectAms(project.getId()),
                        project.getAmUserId(),
                        project.getAmName()),
                walletUsers(
                        mapper.findProjectDataSpecialists(project.getId()),
                        project.getDataSpecialistId(),
                        project.getDataSpecialist()));
    }

    private List<UserReference> walletUsers(
            List<ProjectUserAssignment> assignments, Long legacyId, String legacyName) {
        if (assignments != null && !assignments.isEmpty()) {
            return assignments.stream()
                    .map(item -> new UserReference(string(item.getUserId()), item.getUserName()))
                    .toList();
        }
        return legacyId == null
                ? List.of()
                : List.of(new UserReference(string(legacyId), legacyName));
    }

    private String walletReference(Project project) {
        return project.getWalletCustomerRefId() == null
                        || project.getWalletCustomerRefId().isBlank()
                ? project.getProjectCode()
                : project.getWalletCustomerRefId();
    }

    private Project requireProject(Long id) {
        Project project = mapper.findProject(id);
        if (project == null) {
            throw new ProjectException("项目不存在或已被删除");
        }
        return project;
    }

    private Project requireMutableProject(Long id) {
        Project project = requireProject(id);
        if (TERMINAL_STATUSES.contains(project.getStatus())) {
            throw new ProjectException("结束或归档项目不允许修改或绑定代理线");
        }
        return project;
    }

    private AgencyLine requireAgencyLine(Long id) {
        AgencyLine line = mapper.findAgencyLine(id);
        if (line == null) {
            throw new ProjectException("代理线不存在或已被删除");
        }
        return line;
    }

    private void requireLineMutable(AgencyLine line) {
        if (line.getProjectId() != null) {
            requireMutableProject(line.getProjectId());
        }
    }

    private void validateUserPair(String rawId, String name, String label) {
        boolean hasId = rawId != null && !rawId.isBlank();
        boolean hasName = name != null && !name.isBlank();
        if (hasId != hasName) {
            throw new ProjectException(label + "必须同时保存用户ID和姓名");
        }
        if (hasId && mapper.countActiveUser(requiredId(rawId, label + "用户ID")) != 1) {
            throw new ProjectException(label + "用户不存在或已停用");
        }
    }

    private void requireDictionaryValue(String dictCode, String value) {
        if (mapper.countEnabledDictionaryValue(dictCode, value.trim()) != 1) {
            throw new ProjectException("字典“" + dictCode + "”中不存在启用值：" + value);
        }
    }

    private RegionCountry requireRegionCountry(String countryCode) {
        RegionCountry item =
                mapper.findEnabledRegionCountry(countryCode.trim().toUpperCase(Locale.ROOT));
        if (item == null) {
            throw new ProjectException("投放国家或地区不存在或已停用：" + countryCode);
        }
        return item;
    }

    private List<String> distinctUpper(List<String> values) {
        return values.stream()
                .map(value -> value.trim().toUpperCase(Locale.ROOT))
                .distinct()
                .toList();
    }

    private Set<Long> parseIds(List<String> ids) {
        Set<Long> result = new HashSet<>();
        if (ids != null) {
            ids.forEach(value -> result.add(requiredId(value, "代理线ID")));
        }
        return result;
    }

    private Long optionalId(String value, String label) {
        return value == null || value.isBlank() ? null : requiredId(value, label);
    }

    private Long requiredId(String value, String label) {
        try {
            return Long.valueOf(value.trim());
        } catch (RuntimeException exception) {
            throw new ProjectException(label + "格式不正确");
        }
    }

    private String validateUrl(String raw) {
        String value = trimToNull(raw);
        if (value == null) {
            return null;
        }
        try {
            String scheme = URI.create(value).getScheme();
            if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) {
                throw new IllegalArgumentException();
            }
            return value;
        } catch (RuntimeException exception) {
            throw new ProjectException("链接必须是有效的http(s)地址");
        }
    }

    private List<String> distinctLower(List<String> values) {
        return values.stream().map(this::lower).distinct().toList();
    }

    private List<String> distinctTrimmed(List<String> values) {
        return values.stream().map(String::trim).distinct().toList();
    }

    private String normalizeProjectCode(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    private String lower(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }

    private String optionalLower(String value) {
        return value == null || value.isBlank() ? null : lower(value);
    }

    private String requiredText(String value, String label) {
        String normalized = trimToNull(value);
        if (normalized == null) throw new ProjectException(label + "不能为空");
        return normalized;
    }

    private String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String firstNonBlank(String first, String second) {
        return first != null && !first.isBlank() ? first : second;
    }

    private String string(Long value) {
        return value == null ? null : value.toString();
    }

    private Long currentUserId() {
        return currentUser().userId();
    }

    private String normalizeProjectOptionKeyword(String keyword) {
        String normalizedKeyword = trimToNull(keyword);
        if (normalizedKeyword != null && normalizedKeyword.length() > 100) {
            throw new ProjectException("项目搜索关键词不能超过100个字符");
        }
        return normalizedKeyword;
    }

    /** 管理员不限制数据范围，其他用户按本人主部门及其完整下级部门过滤。 */
    private Long dataScopeUserId() {
        CurrentUser user = currentUser();
        boolean unrestricted =
                user.authorities().stream()
                        .map(authority -> authority.getAuthority())
                        .anyMatch(
                                authority ->
                                        "ROLE_ADMIN".equals(authority)
                                                || "ROLE_MINI_ADMIN".equals(authority));
        return unrestricted ? null : user.userId();
    }

    private CurrentUser currentUser() {
        if (SecurityContextHolder.getContext().getAuthentication() == null) {
            throw new ProjectException("当前会话未认证");
        }
        Object principal = SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (!(principal instanceof CurrentUser user)) {
            throw new ProjectException("当前会话未认证");
        }
        return user;
    }

    private IntegrationSecretCipher requireCipher() {
        if (cipher == null) throw new ProjectException("代理线令牌加密组件不可用");
        return cipher;
    }

    private String decryptToken(String ciphertext) {
        if (ciphertext == null || ciphertext.isBlank()) return "";
        return requireCipher().decrypt(ciphertext);
    }

    private static final class ProjectOptionBuilder {
        private final Long id;
        private final String name;
        private final String projectCode;
        private final String status;
        private final List<String> platforms = new java.util.ArrayList<>();

        private ProjectOptionBuilder(Long id, String name, String projectCode, String status) {
            this.id = id;
            this.name = name;
            this.projectCode = projectCode;
            this.status = status;
        }

        private ProjectViews.ProjectOption view() {
            return new ProjectViews.ProjectOption(
                    id.toString(), name, projectCode, status, List.copyOf(platforms));
        }
    }

    private static final class RegionOptionBuilder {
        private final String code;
        private final String name;
        private final List<ProjectViews.CountryOption> countries = new java.util.ArrayList<>();

        private RegionOptionBuilder(String code, String name) {
            this.code = code;
            this.name = name;
        }

        private ProjectViews.RegionOption view() {
            return new ProjectViews.RegionOption(code, name, List.copyOf(countries));
        }
    }

    /** 可安全展示给前端的项目业务异常。 */
    public static class ProjectException extends RuntimeException {
        public ProjectException(String message) {
            super(message);
        }
    }
}
