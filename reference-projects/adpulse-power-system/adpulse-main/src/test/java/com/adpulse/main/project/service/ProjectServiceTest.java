package com.adpulse.main.project.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.main.project.dto.ProjectRequests.AgencyLinePatch;
import com.adpulse.main.project.dto.ProjectRequests.AgencyLineSave;
import com.adpulse.main.project.dto.ProjectRequests.KpiSave;
import com.adpulse.main.project.dto.ProjectRequests.ProjectSave;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.AgencyLine;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.model.ProjectOptionRow;
import com.adpulse.main.project.model.ProjectStatisticsRow;
import com.adpulse.main.project.model.RegionCountry;
import com.adpulse.main.project.service.ProjectService.ProjectException;
import com.adpulse.main.safeheron.service.SafeheronWalletService;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 项目状态及代理线归属规则测试。 */
@ExtendWith(MockitoExtension.class)
class ProjectServiceTest {
    @Mock private ProjectMapper mapper;
    @Mock private SafeheronWalletService walletService;
    @Mock private ProjectSpendQueryProvider spendQueryProvider;

    private ProjectService service;

    @BeforeEach
    void setUp() {
        service = new ProjectService(mapper, walletService, spendQueryProvider);
        org.mockito.Mockito.lenient().when(mapper.countActiveUser(9L)).thenReturn(1);
        CurrentUser user = new CurrentUser(9L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldSearchUnboundOptionsWithNormalizedKeywordWithoutLoadingDetails() {
        var option =
                new com.adpulse.main.project.dto.ProjectViews.AgencyLineOption(
                        "9007199254740993", "代理线");
        when(mapper.findUnboundAgencyLineOptions("代理线")).thenReturn(List.of(option));

        assertThat(service.listUnboundAgencyLineOptions(" 代理线 ")).containsExactly(option);
        verify(mapper).findUnboundAgencyLineOptions("代理线");
        org.mockito.Mockito.verifyNoMoreInteractions(mapper);
    }

    @Test
    void shouldTreatBlankAndNullOptionSearchAsInitialQuery() {
        when(mapper.findUnboundAgencyLineOptions(null)).thenReturn(List.of());

        assertThat(service.listUnboundAgencyLineOptions("  ")).isEmpty();
        assertThat(service.listUnboundAgencyLineOptions(null)).isEmpty();
    }

    @Test
    void shouldListProjectsWithoutLoadingAgencyLines() {
        Project project = project(1L, "active");
        project.setProductInfo("测试产品");
        when(mapper.findProjects(null, null, null, 0, 20)).thenReturn(List.of(project));
        when(mapper.countProjects(null, null, null)).thenReturn(1L);

        var result = service.listProjects(null, null, null, 1, 20);

        assertThat(result.total()).isEqualTo(1);
        assertThat(result.items()).hasSize(1);
        assertThat(result.items().getFirst().agencyLineIds()).isEmpty();
        assertThat(result.items().getFirst().agentLines()).isEmpty();
        verify(mapper, never()).findAgencyLines(null, null, null, 1L, null, 0, Integer.MAX_VALUE);
    }

    @ParameterizedTest
    @ValueSource(ints = {999_999, 1_000_000})
    void shouldUseFullOptionPageSizeAsProjectPageUpperBound(int requestedPageSize) {
        var result = service.listProjects(null, null, null, 1, requestedPageSize);

        assertThat(result.pageSize()).isEqualTo(999_999);
        verify(mapper).findProjects(null, null, null, 9L, 0, 999_999);
    }

    @Test
    void shouldCountTabsBeyondListPageLimitWithoutLoadingDetails() {
        when(mapper.countProjects(null, null, null)).thenReturn(1200L);
        when(mapper.countAgencyLines(null, null, null, null, null)).thenReturn(5000L);

        var result = service.getTabCounts();

        assertThat(result.projectCount()).isEqualTo(1200);
        assertThat(result.agencyLineCount()).isEqualTo(5000);
        verify(mapper).countProjects(null, null, null);
        verify(mapper).countAgencyLines(null, null, null, null, null);
        org.mockito.Mockito.verifyNoMoreInteractions(mapper);
    }

    @Test
    void shouldReturnZeroCountsForEmptyTabs() {
        var result = service.getTabCounts();

        assertThat(result.projectCount()).isZero();
        assertThat(result.agencyLineCount()).isZero();
    }

    @Test
    void shouldLoadAgencyLinesWhenViewingProject() {
        Project project = project(1L, "active");
        project.setProductInfo("测试产品");
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        line.setLineName("测试代理线");
        when(mapper.findProject(1L)).thenReturn(project);
        when(mapper.findAgencyLines(null, null, null, 1L, null, 0, Integer.MAX_VALUE))
                .thenReturn(List.of(line));

        var result = service.getProject(1L);

        assertThat(result.agencyLineIds()).containsExactly("2");
        assertThat(result.agentLines()).containsExactly("测试代理线");
    }

    @Test
    void shouldBatchPageRelationsWithoutMixingProjects() {
        Project first = project(1L, "active");
        first.setProjectCode("P1");
        first.setProductInfo("产品一");
        Project second = project(2L, "pending");
        second.setProjectCode("P2");
        second.setProductInfo("产品二");
        second.setAmUserId(9L);
        second.setAmName("历史 AM");
        var ids = List.of(1L, 2L);
        when(mapper.findProjects(null, null, null, 0, 20)).thenReturn(List.of(first, second));
        when(mapper.countProjects(null, null, null)).thenReturn(2L);
        when(mapper.findPlatformsByProjectIds(ids))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.model.ProjectReadRows.Value(
                                        2L, "google"),
                                new com.adpulse.main.project.model.ProjectReadRows.Value(
                                        1L, "facebook")));
        when(mapper.findProductLinksByProjectIds(ids))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.model.ProjectReadRows.Value(
                                        1L, "https://one.example"),
                                new com.adpulse.main.project.model.ProjectReadRows.Value(
                                        1L, "https://two.example")));
        when(mapper.findKpisByProjectIds(ids))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.model.ProjectReadRows.Kpi(
                                        1L, "CPA", "between", BigDecimal.ONE, BigDecimal.TEN)));
        when(mapper.findProjectAmsByProjectIds(ids))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.model.ProjectReadRows.User(
                                        1L, 3L, "AM 一"),
                                new com.adpulse.main.project.model.ProjectReadRows.User(
                                        1L, 4L, "AM 二")));

        var page = service.listProjects(null, null, null, 1, 20);

        assertThat(page.items()).extracting(item -> item.id()).containsExactly("1", "2");
        assertThat(page.items().getFirst().platforms()).containsExactly("facebook");
        assertThat(page.items().getLast().platforms()).containsExactly("google");
        assertThat(page.items().getFirst().productLinks())
                .containsExactly("https://one.example", "https://two.example");
        assertThat(page.items().getLast().productLinks()).isEmpty();
        assertThat(page.items().getFirst().kpiRequirements().getFirst().targetMax())
                .isEqualByComparingTo(BigDecimal.TEN);
        assertThat(page.items().getFirst().amUsers())
                .extracting(item -> item.userId())
                .containsExactly("3", "4");
        assertThat(page.items().getLast().amUsers())
                .extracting(item -> item.userId())
                .containsExactly("9");
        verify(mapper, never()).findPlatforms(any());
        verify(mapper, never()).findKpis(any());
        verify(mapper, never()).findProjectAms(any());
        verify(walletService, never()).findProjectWallet(any());
        verify(walletService).findProjectWallets(List.of("P1", "P2"));
    }

    @Test
    void shouldSkipRelationsForEmptyProjectPage() {
        var page = service.listProjects(null, null, null, 1, 20);
        assertThat(page.items()).isEmpty();
        verify(mapper, never()).findPlatformsByProjectIds(any());
        verify(mapper, never()).findKpisByProjectIds(any());
        org.mockito.Mockito.verifyNoInteractions(walletService);
    }

    @Test
    void shouldRejectBindingsForEndedProject() {
        Project project = project(1L, "ended");
        when(mapper.findProject(1L)).thenReturn(project);

        assertThatThrownBy(
                        () ->
                                service.patchAgencyLines(
                                        1L, new AgencyLinePatch(List.of("2"), List.of(), "r1")))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessageContaining("结束或归档");
    }

    @Test
    void shouldRejectAgencyLineAlreadyOwnedByAnotherProject() {
        Project project = project(1L, "active");
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        line.setProjectId(3L);
        line.setLineName("Facebook主线");
        line.setPlatformValue("facebook");
        when(mapper.findProject(1L)).thenReturn(project);
        when(mapper.findAgencyLine(2L)).thenReturn(line);

        assertThatThrownBy(
                        () ->
                                service.patchAgencyLines(
                                        1L, new AgencyLinePatch(List.of("2"), List.of(), "r1")))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessageContaining("已关联其他项目");
    }

    @Test
    void shouldReturnLightweightProjectContext() {
        ProjectOptionRow facebook = optionRow(1L, "PRJ-1", "项目一", "active", "facebook");
        ProjectOptionRow google = optionRow(1L, "PRJ-1", "项目一", "active", "google");
        ProjectStatisticsRow statistics = new ProjectStatisticsRow();
        statistics.setTotal(4L);
        statistics.setActive(1L);
        statistics.setDraftOrPending(2L);
        statistics.setEndedOrArchived(1L);
        when(mapper.countProjectStatuses()).thenReturn(statistics);
        when(mapper.findProjectOptionRows()).thenReturn(List.of(facebook, google));

        var context = service.getProjectContext();

        assertThat(context.statistics().total()).isEqualTo(4);
        assertThat(context.statistics().draftOrPending()).isEqualTo(2);
        assertThat(context.options()).hasSize(1);
        assertThat(context.options().getFirst().platforms()).containsExactly("facebook", "google");
    }

    @Test
    void shouldPersistAgencyLinePageIdDuringUpdate() {
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        line.setLineName("旧代理线");
        line.setPlatformValue("facebook");
        line.setPixelName("旧像素");
        line.setOptimizerId(3L);
        line.setOptimizerName("旧优化师");
        when(mapper.findAgencyLine(2L)).thenReturn(line);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findUserReference(3L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(3L, "张三", 1));

        service.updateAgencyLine(
                2L,
                new AgencyLineSave(
                        "2",
                        null,
                        "Facebook主线",
                        "facebook",
                        "https://example.com/landing-page",
                        " 123456789 ",
                        null,
                        "3",
                        "张三"));

        assertThat(line.getPageId()).isEqualTo("123456789");
        assertThat(line.getPixelName()).isNull();
        verify(mapper).updateAgencyLine(line);
    }

    @Test
    void shouldRejectDuplicateActiveProjectNameWhenCreating() {
        ProjectSave request = projectSave(" 重名项目 ");
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        when(mapper.countActiveProjectName("重名项目", null)).thenReturn(1);

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("项目名称已存在，请使用其他名称");

        verify(mapper, never()).insertProject(any());
    }

    @Test
    void shouldRequireOutsourcingTeamForOutsourcedProject() {
        ProjectSave request = projectSave("外包项目", true, List.of());
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("有外包项目必须至少选择一个外包团队");

        verify(mapper, never()).insertProject(any());
    }

    @Test
    void shouldExcludeCurrentProjectWhenCheckingNameDuringUpdate() {
        Project project = project(1L, "active");
        project.setProjectName("原项目");
        when(mapper.findProject(1L)).thenReturn(project);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());

        assertThat(service.updateProject(1L, projectSave("原项目")).name()).isEqualTo("原项目");

        verify(mapper).countActiveProjectName("原项目", 1L);
    }

    @Test
    void shouldRejectDisabledProjectCountry() {
        ProjectSave request = projectSave("地区错误项目");
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("投放国家或地区不存在或已停用：US");

        verify(mapper, never()).insertProject(any());
    }

    @Test
    void shouldFailProjectCreationWhenRequestedWalletCannotBeCreated() {
        ProjectSave request = projectSaveWithWallet("钱包项目");
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        doThrow(new SafeheronWalletService.SafeheronWalletException("Safeheron钱包创建失败，请稍后重试"))
                .when(walletService)
                .createProjectWallet("PRJ-1", "钱包项目");

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("Safeheron钱包创建失败，请稍后重试");

        verify(walletService).createProjectWallet("PRJ-1", "钱包项目");
    }

    @Test
    void shouldCreateWalletForExistingProject() {
        Project project = project(1L, "active");
        project.setProjectCode("PRJ-1");
        project.setProjectName("钱包项目");
        var wallet =
                new com.adpulse.main.project.dto.ProjectViews.ProjectWallet(
                        "7", "account-key", "0x123", "T123", "TRX", "钱包项目");
        when(mapper.findProject(1L)).thenReturn(project);
        when(walletService.createProjectWallet("PRJ-1", "钱包项目")).thenReturn(wallet);

        assertThat(service.createProjectWallet(1L)).isEqualTo(wallet);
        verify(walletService).createProjectWallet("PRJ-1", "钱包项目");
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({
        "true,1,false",
        "true,0,true",
        "false,0,false",
        "null,0,false"
    })
    void shouldApplyDictionarySwitchWhenCreatingProject(
            String requested, int disabledCount, boolean expectedCreation) {
        ProjectSave request = org.mockito.Mockito.spy(projectSaveWithWallet("钱包项目"));
        when(request.createWallet())
                .thenReturn("null".equals(requested) ? null : Boolean.valueOf(requested));
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        if ("true".equals(requested)) {
            when(mapper.countEnabledDictionaryValue("PROJECT_CREATE_WALLET", "0"))
                    .thenReturn(disabledCount);
        }
        org.mockito.Mockito.doAnswer(
                        invocation -> {
                            Project inserted = invocation.getArgument(0);
                            inserted.setId(1L);
                            return 1;
                        })
                .when(mapper)
                .insertProject(any());
        Project saved = project(1L, "active");
        saved.setProjectCode("PRJ-1");
        saved.setProductInfo("产品信息");
        when(mapper.findProject(1L)).thenReturn(saved);

        assertThat(service.createProject(request).id()).isEqualTo("1");

        verify(mapper).insertProject(any());
        verify(walletService, org.mockito.Mockito.times(expectedCreation ? 1 : 0))
                .createProjectWallet("PRJ-1", "钱包项目");
        if (!"true".equals(requested)) {
            verify(mapper, never()).countEnabledDictionaryValue("PROJECT_CREATE_WALLET", "0");
        }
    }

    @Test
    void shouldRejectDuplicateKpiMetrics() {
        ProjectSave request =
                projectSave(
                        "重复KPI项目",
                        List.of(
                                new KpiSave("CPP", ">", BigDecimal.ONE, null),
                                new KpiSave("cpp", "<=", BigDecimal.TEN, null)));

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("每个KPI指标只能配置一次");
    }

    @Test
    void shouldRejectDraftStatusWhenCreating() {
        ProjectSave request = org.mockito.Mockito.spy(projectSave("草稿项目"));
        when(request.status()).thenReturn("draft");

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("项目状态不合法");
        verify(mapper, never()).insertProject(any());
    }

    @Test
    void shouldRejectDraftStatusWhenUpdating() {
        Project existing = project(1L, "active");
        when(mapper.findProject(1L)).thenReturn(existing);
        ProjectSave request = org.mockito.Mockito.spy(projectSave("进行中项目"));
        when(request.status()).thenReturn("draft");

        assertThatThrownBy(() -> service.updateProject(1L, request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("项目状态不合法");
        verify(mapper, never()).updateProject(any());
    }

    @Test
    void shouldRejectInvalidKpiRange() {
        ProjectSave request =
                projectSave(
                        "错误区间项目",
                        List.of(new KpiSave("ROAS", "between", BigDecimal.TEN, BigDecimal.ONE)));

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("KPI区间下限必须小于上限");
    }

    @Test
    void shouldRejectUpperTargetForNonRangeKpi() {
        ProjectSave request =
                projectSave(
                        "多余上限项目", List.of(new KpiSave("CPA", "=", BigDecimal.ONE, BigDecimal.TEN)));

        assertThatThrownBy(() -> service.createProject(request))
                .isInstanceOf(ProjectService.ProjectException.class)
                .hasMessage("非区间KPI不能设置上限值");
    }

    @Test
    void shouldBuildRegionCountryTreeInConfiguredOrder() {
        RegionCountry canada = regionCountry();
        canada.setCountryCode("CA");
        canada.setCountryName("加拿大");
        when(mapper.findEnabledRegionCountries()).thenReturn(List.of(regionCountry(), canada));

        var options = service.listRegionOptions();

        assertThat(options).hasSize(1);
        assertThat(options.getFirst().code()).isEqualTo("NORTH_AMERICA");
        assertThat(options.getFirst().countries()).extracting("code").containsExactly("US", "CA");
    }

    private ProjectSave projectSave(String name) {
        return projectSave(name, false, List.of());
    }

    private ProjectSave projectSave(String name, List<KpiSave> kpis) {
        return new ProjectSave(
                "PRJ-1",
                name,
                "game",
                List.of("https://example.com/product"),
                "投放组",
                null,
                null,
                null,
                null,
                false,
                List.of(),
                "normal",
                List.of("facebook"),
                List.of("US"),
                BigDecimal.TEN,
                "active",
                "产品信息",
                null,
                false,
                kpis,
                null,
                null,
                List.of(
                        new com.adpulse.main.project.dto.ProjectRequests.UserAssignmentSave(
                                "9", "项目AM")),
                List.of());
    }

    private ProjectSave projectSaveWithWallet(String name) {
        ProjectSave base = projectSave(name);
        return new ProjectSave(
                base.projectCode(),
                base.name(),
                base.projectType(),
                base.productLinks(),
                base.responsibleTeam(),
                base.amUserId(),
                base.amName(),
                base.deliveryLeaderId(),
                base.deliveryLeaderName(),
                base.isOutsourced(),
                base.outsourcingTeams(),
                base.priority(),
                base.platforms(),
                base.countryRegions(),
                base.serviceFeePercent(),
                base.status(),
                base.productInfo(),
                base.customerDailyReportUrl(),
                true,
                base.kpiRequirements(),
                null,
                null,
                base.amUsers(),
                base.dataSpecialists());
    }

    private ProjectSave projectSave(
            String name, boolean isOutsourced, List<String> outsourcingTeams) {
        return projectSaveWithPeople(name, isOutsourced, outsourcingTeams, null, null);
    }

    private ProjectSave projectSaveWithPeople(
            String name,
            boolean isOutsourced,
            List<String> outsourcingTeams,
            String specialistId,
            String specialistName) {
        return new ProjectSave(
                "PRJ-1",
                name,
                "game",
                List.of("https://example.com/product"),
                "投放组",
                null,
                null,
                null,
                null,
                isOutsourced,
                outsourcingTeams,
                "normal",
                List.of("facebook"),
                List.of("US"),
                BigDecimal.TEN,
                "active",
                "产品信息",
                null,
                false,
                List.of(new KpiSave("ROAS", ">=", BigDecimal.ONE, null)),
                specialistId,
                specialistName,
                List.of(
                        new com.adpulse.main.project.dto.ProjectRequests.UserAssignmentSave(
                                "9", "项目AM")),
                specialistId == null
                        ? List.of()
                        : List.of(
                                new com.adpulse.main.project.dto.ProjectRequests.UserAssignmentSave(
                                        specialistId, specialistName)));
    }

    @Test
    void shouldSaveSelectedAmAndOptionalSpecialist() {
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        when(mapper.countActiveUser(12L)).thenReturn(1);
        when(mapper.countActiveUser(10L)).thenReturn(1);
        when(mapper.insertProject(any()))
                .thenAnswer(
                        invocation -> {
                            Project saved = invocation.getArgument(0);
                            saved.setId(1L);
                            when(mapper.findProject(1L)).thenReturn(saved);
                            return 1;
                        });
        var request =
                org.mockito.Mockito.spy(
                        projectSaveWithPeople("新项目", false, List.of(), "12", "数据用户"));
        when(request.amUserId()).thenReturn("99");
        when(request.amName()).thenReturn("请求伪造的AM");
        when(request.amUsers())
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.dto.ProjectRequests.UserAssignmentSave(
                                        "9", "项目AM"),
                                new com.adpulse.main.project.dto.ProjectRequests.UserAssignmentSave(
                                        "10", "第二AM")));
        var result = service.createProject(request);
        assertThat(result.amUserId()).isEqualTo("9");
        assertThat(result.amName()).isEqualTo("项目AM");
        assertThat(result.dataSpecialistId()).isEqualTo("12");
        assertThat(result.dataSpecialist()).isEqualTo("数据用户");
        verify(mapper).insertProjectAm(1L, 9L, "项目AM", 0, 9L);
        verify(mapper).insertProjectAm(1L, 10L, "第二AM", 1, 9L);
    }

    @Test
    void shouldRejectUnavailableSpecialist() {
        assertThatThrownBy(
                        () ->
                                service.createProject(
                                        projectSaveWithPeople(
                                                "新项目", false, List.of(), "12", "数据用户")))
                .hasMessage("数据专员用户不存在或已停用");
        verify(mapper, never()).insertProject(any());
    }

    @Test
    void shouldRejectSpecialistWithoutStableId() {
        var request =
                org.mockito.Mockito.spy(
                        projectSaveWithPeople("新项目", false, List.of(), null, "数据用户"));
        when(request.dataSpecialists()).thenReturn(null);
        assertThatThrownBy(() -> service.createProject(request)).hasMessage("数据专员必须同时保存用户ID和姓名");
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.NullAndEmptySource
    @org.junit.jupiter.params.provider.ValueSource(strings = {" ", "\t"})
    void shouldCreateUnassignedLine(String id) {
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.insertAgencyLine(any()))
                .thenAnswer(
                        call -> {
                            AgencyLine saved = call.getArgument(0);
                            saved.setId(2L);
                            when(mapper.findAgencyLine(2L)).thenReturn(saved);
                            return 1;
                        });
        var result = service.createAgencyLine(lineSave(id, id), null, null);
        assertThat(result.optimizerId()).isNull();
        assertThat(result.optimizerName()).isNull();
        assertThat(result.optimizerStatus()).isNull();
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(
            strings = {"bad", "0", "-1", "999", "999999999999999999999999"})
    void shouldRejectInvalidOptimizer(String id) {
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        assertThatThrownBy(() -> service.createAgencyLine(lineSave(id, "姓名"), null, null))
                .isInstanceOf(ProjectException.class);
        verify(mapper, never()).insertAgencyLine(any());
    }

    @Test
    void shouldRejectNameWithoutId() {
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        assertThatThrownBy(() -> service.createAgencyLine(lineSave(null, "姓名"), null, null))
                .hasMessageContaining("不能缺少用户ID");
    }

    @Test
    void shouldPreserveDisabledHistoricalOptimizerAndSnapshot() {
        AgencyLine line = editableLine();
        when(mapper.findUserReference(3L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(3L, "当前姓名", 0));
        var result = service.updateAgencyLine(2L, lineSave("3", null));
        assertThat(result.optimizerId()).isEqualTo("3");
        assertThat(result.optimizerName()).isEqualTo("原姓名");
        assertThat(result.optimizerStatus()).isZero();
        verify(mapper).updateAgencyLine(line);
    }

    @Test
    void shouldRejectCreatingOrChangingToDisabledOptimizer() {
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findUserReference(4L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(4L, "停用人员", 0));
        assertThatThrownBy(() -> service.createAgencyLine(lineSave("4", "姓名"), null, null))
                .isInstanceOf(ProjectException.class);
        editableLine();
        assertThatThrownBy(() -> service.updateAgencyLine(2L, lineSave("4", "姓名")))
                .isInstanceOf(ProjectException.class);
        verify(mapper, never()).updateAgencyLine(any());
    }

    @Test
    void shouldRejectDeletedOriginalButAllowClearingAndReassignment() {
        AgencyLine line = editableLine();
        assertThatThrownBy(() -> service.updateAgencyLine(2L, lineSave("3", null)))
                .isInstanceOf(ProjectException.class);
        var cleared = service.updateAgencyLine(2L, lineSave(null, null));
        assertThat(cleared.optimizerId()).isNull();
        assertThat(line.getOptimizerName()).isNull();
        when(mapper.findUserReference(4L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(4L, "新人员", 1));
        var reassigned = service.updateAgencyLine(2L, lineSave("4", null));
        assertThat(reassigned.optimizerId()).isEqualTo("4");
        assertThat(reassigned.optimizerName()).isEqualTo("新人员");
    }

    @Test
    void shouldKeepUnassignedLineInList() {
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        when(mapper.findAgencyLines(List.of(), null, null, null, null, 0, 20))
                .thenReturn(List.of(line));
        when(mapper.countAgencyLines(List.of(), null, null, null, null)).thenReturn(1L);
        var result = service.listAgencyLines(null, null, null, null, null, 1, 20);
        assertThat(result.items()).hasSize(1);
        assertThat(result.items().getFirst().optimizerId()).isNull();
    }

    @Test
    void shouldSearchAgencyLinesByDistinctMultilineKeywordsAndOptimizer() {
        List<String> keywords = List.of("https://example.com/a", "https://example.com/b");
        when(mapper.findAgencyLines(keywords, null, null, null, 9L, 0, 20)).thenReturn(List.of());
        when(mapper.countAgencyLines(keywords, null, null, null, 9L)).thenReturn(0L);

        service.listAgencyLines(
                " https://example.com/a\r\n\nhttps://example.com/b\nhttps://example.com/a ",
                null,
                null,
                null,
                9L,
                1,
                20);

        verify(mapper).findAgencyLines(keywords, null, null, null, 9L, 0, 20);
        verify(mapper).countAgencyLines(keywords, null, null, null, 9L);
    }

    @Test
    void shouldRejectTooManyAgencyLineKeywords() {
        String keywords =
                java.util.stream.IntStream.rangeClosed(1, 101)
                        .mapToObj(String::valueOf)
                        .collect(java.util.stream.Collectors.joining("\n"));

        assertThatThrownBy(() -> service.listAgencyLines(keywords, null, null, null, null, 1, 20))
                .isInstanceOf(ProjectException.class)
                .hasMessage("关键词最多输入100行");
    }

    @Test
    void shouldPreserveProductOriginalAndKpiWithKwaiAndExplicitSpecialistClear() {
        Project existing = project(1L, "pending");
        existing.setDataSpecialistId(12L);
        when(mapper.findProject(1L)).thenReturn(existing);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "tiktok")).thenReturn(1);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "kwai")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        var request = org.mockito.Mockito.spy(projectSave("项目"));
        String original = " \n" + "中".repeat(980) + "😀\n  ";
        when(request.productInfo()).thenReturn(original);
        when(request.platforms()).thenReturn(List.of("facebook", "tiktok", "kwai"));
        when(request.status()).thenReturn("pending");
        when(request.projectType()).thenReturn("other");
        when(request.responsibleTeam()).thenReturn("MP投放部");
        when(request.dataSpecialistId()).thenReturn("12");
        when(request.dataSpecialist()).thenReturn("旧数据专员");
        when(request.dataSpecialists()).thenReturn(List.of());
        when(request.kpiRequirements())
                .thenReturn(List.of(new KpiSave("CPP", "<", BigDecimal.TEN, null)));
        service.updateProject(1L, request);
        assertThat(existing.getProductInfo()).isEqualTo(original);
        assertThat(existing.getDataSpecialistId()).isNull();
        assertThat(existing.getStatus()).isEqualTo("pending");
        assertThat(existing.getProjectType()).isEqualTo("other");
        assertThat(existing.getResponsibleTeam()).isEqualTo("MP投放部");
        verify(mapper).insertKpi(1L, "CPP", "<", BigDecimal.TEN, null, 0, 9L);
    }

    @Test
    void shouldValidateProductUtf16LengthWithoutTrimming() {
        try (var factory = jakarta.validation.Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            for (String allowed : List.of("中".repeat(986), "中".repeat(2000), "😀".repeat(1000))) {
                assertThat(validator.validateValue(ProjectSave.class, "productInfo", allowed))
                        .isEmpty();
            }
            for (String rejected : List.of("中".repeat(2001), "😀".repeat(1000) + "中", "   ")) {
                assertThat(validator.validateValue(ProjectSave.class, "productInfo", rejected))
                        .isNotEmpty();
            }
        }
    }

    private AgencyLine editableLine() {
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        line.setOptimizerId(3L);
        line.setOptimizerName("原姓名");
        when(mapper.findAgencyLine(2L)).thenReturn(line);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        return line;
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(ints = {0, 1})
    void shouldClearExistingAssignmentWithoutChangingUserStatus(int status) {
        AgencyLine line = editableLine();
        line.setOptimizerStatus(status);
        var cleared = service.updateAgencyLine(2L, lineSave(" ", " "));
        assertThat(cleared.optimizerId()).isNull();
        assertThat(cleared.optimizerName()).isNull();
        verify(mapper, never()).findUserReference(any());
    }

    @Test
    void shouldRejectEmptyAmArrayEvenWithLegacyId() {
        var request = org.mockito.Mockito.spy(projectSave("项目"));
        when(request.amUsers()).thenReturn(List.of());
        when(request.amUserId()).thenReturn("9");
        when(request.amName()).thenReturn("旧AM");
        assertThatThrownBy(() -> service.createProject(request)).hasMessage("AM至少选择一名用户");
    }

    @Test
    void shouldRejectKwaiLineOutsideProjectPlatforms() {
        when(mapper.findProject(1L)).thenReturn(project(1L, "pending"));
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "kwai")).thenReturn(1);
        when(mapper.findPlatforms(1L)).thenReturn(List.of("facebook"));
        var request = new AgencyLineSave(null, "1", "Kwai线", "kwai", null, null, null, null, null);
        assertThatThrownBy(() -> service.createAgencyLine(request, null, null))
                .hasMessage("代理线平台不在项目投放范围内");
        verify(mapper, never()).insertAgencyLine(any());
    }

    private AgencyLineSave lineSave(String optimizerId, String optimizerName) {
        return new AgencyLineSave(
                "999",
                null,
                "代理线",
                "facebook",
                "https://example.com",
                "主页",
                "像素",
                optimizerId,
                optimizerName);
    }

    @Test
    void shouldClearOptionalSpecialistOnUpdate() {
        Project existing = project(1L, "active");
        existing.setDataSpecialistId(12L);
        existing.setDataSpecialist("数据用户");
        when(mapper.findProject(1L)).thenReturn(existing);
        when(mapper.countEnabledDictionaryValue("AD_MEDIA", "facebook")).thenReturn(1);
        when(mapper.findEnabledRegionCountry("US")).thenReturn(regionCountry());
        var result = service.updateProject(1L, projectSave("项目"));
        assertThat(result.dataSpecialistId()).isNull();
        assertThat(result.dataSpecialist()).isNull();
    }

    private ProjectOptionRow optionRow(
            Long id, String code, String name, String status, String platform) {
        ProjectOptionRow row = new ProjectOptionRow();
        row.setId(id);
        row.setProjectCode(code);
        row.setProjectName(name);
        row.setStatus(status);
        row.setPlatformValue(platform);
        return row;
    }

    private Project project(Long id, String status) {
        Project project = new Project();
        project.setId(id);
        project.setStatus(status);
        return project;
    }

    private RegionCountry regionCountry() {
        RegionCountry item = new RegionCountry();
        item.setRegionCode("NORTH_AMERICA");
        item.setRegionName("北美洲");
        item.setCountryCode("US");
        item.setCountryName("美国");
        return item;
    }
}
