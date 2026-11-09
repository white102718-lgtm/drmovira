package com.adpulse.main.deliveryreport;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.*;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 覆盖日报身份隔离、精确匹配、补录合并与截图边界。 */
class DeliveryReportServiceTest {
    private final DeliveryReportMapper mapper = mock(DeliveryReportMapper.class);
    private final DeliveryReportQueryProvider provider = mock(DeliveryReportQueryProvider.class);
    private final ObjectMapper json = new ObjectMapper();
    private final DeliveryReportService service = new DeliveryReportService(mapper, provider, json);
    private final LocalDate date = LocalDate.of(2026, 9, 9);
    private final LineOption line = new LineOption("10", "Project", "20", "Line");

    @BeforeEach
    void setUp() {
        var user = new CurrentUser(7L, "session", "投手", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, null, List.of()));
        when(mapper.findEnglishName(7L)).thenReturn(" Alice ");
        when(mapper.findReadEnglishName(7L)).thenReturn(" Alice ");
        when(mapper.findOperatorReporters(7L)).thenReturn(List.of(new Reporter("7", "投手")));
        when(mapper.lockReporter(7L)).thenReturn(7L);
        when(mapper.findLines()).thenReturn(List.of(line));
        when(mapper.findRecords(7L, date)).thenReturn(List.of());
        when(provider.query(date, "Alice")).thenReturn(List.of(platform()));
        doAnswer(
                        invocation -> {
                            ((DeliveryReportRecord) invocation.getArgument(0)).setId(1L);
                            return null;
                        })
                .when(mapper)
                .upsert(any());
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void usesSessionIdentityAndMatchesProjectAndLineTogether() {
        when(provider.query(date, "Alice"))
                .thenReturn(
                        List.of(
                                platform(),
                                new PlatformRow(
                                        "Other",
                                        "Line",
                                        "facebook",
                                        BigDecimal.TEN,
                                        0,
                                        0,
                                        0,
                                        0,
                                        0,
                                        List.of(),
                                        List.of())));
        Result result = service.query(date);
        assertThat(result.rows()).hasSize(1);
        assertThat(result.unmatchedCount()).isEqualTo(1);
        assertThat(result.reporterId()).isEqualTo("7");
        verify(provider).query(date, "Alice");
        verify(mapper).findRecords(7L, date);
    }

    @Test
    void ambiguousNamesAreHiddenRatherThanAssignedToFirstLine() {
        when(mapper.findLines())
                .thenReturn(List.of(line, new LineOption("11", "Project", "21", "Line")));
        assertThat(service.query(date).rows()).isEmpty();
        assertThat(service.query(date).unmatchedCount()).isEqualTo(1);
    }

    @Test
    void preservesManualSpendAndAttachmentsWhenPlatformArrives() throws Exception {
        DeliveryReportRecord saved = record();
        when(mapper.findRecords(7L, date)).thenReturn(List.of(saved));
        when(mapper.findAttachments(1L))
                .thenReturn(List.of(new Attachment("8", "截图.png", "image/png")));
        Row result = service.query(date).rows().getFirst();
        assertThat(result.actualSpend()).isEqualByComparingTo("100");
        assertThat(result.metrics().dailySpend()).isEqualByComparingTo("90");
        assertThat(result.attachments()).hasSize(1);
        assertThat(result.saved()).isTrue();
        assertThat(result.accountIds()).containsExactly("account");
    }

    @Test
    void retainsManualRowsWithZeroActualSpendWhenPlatformHasNoRows() throws Exception {
        when(provider.query(date, "Alice")).thenReturn(List.of());
        when(mapper.findRecords(7L, date)).thenReturn(List.of(record()));
        var row = service.query(date).rows().getFirst();
        assertThat(row.actualSpend()).isEqualTo(new BigDecimal("0.00"));
        assertThat(row.metrics().dailySpend()).isEqualByComparingTo("90");
    }

    @Test
    void rejectsDuplicateRowsAndCrossProjectLine() {
        SaveRow row = new SaveRow(10L, 20L, "facebook", metrics(), List.of());
        assertThatThrownBy(() -> service.save(new SaveRequest(date, List.of(row, row))))
                .hasMessageContaining("只能保存一条");
        assertThatThrownBy(
                        () ->
                                service.save(
                                        new SaveRequest(
                                                date,
                                                List.of(
                                                        new SaveRow(
                                                                99L,
                                                                20L,
                                                                "facebook",
                                                                metrics(),
                                                                List.of())))))
                .hasMessageContaining("不属于");
    }

    @Test
    void rejectsForeignMissingOrNonImageAttachmentsAndOverLimit() {
        when(mapper.lockOwnedImages(eq(7L), anyList())).thenReturn(List.of());
        assertThatThrownBy(
                        () ->
                                service.save(
                                        new SaveRequest(
                                                date,
                                                List.of(
                                                        new SaveRow(
                                                                10L,
                                                                20L,
                                                                "facebook",
                                                                metrics(),
                                                                List.of(8L))))))
                .hasMessageContaining("截图不存在");
        assertThatThrownBy(
                        () ->
                                service.save(
                                        new SaveRequest(
                                                date,
                                                List.of(
                                                        new SaveRow(
                                                                10L,
                                                                20L,
                                                                "facebook",
                                                                metrics(),
                                                                List.of(1L, 2L, 3L, 4L, 5L, 6L))))))
                .hasMessageContaining("最多关联5张");
        verify(mapper, never()).upsert(any());
    }

    @Test
    void acceptsFiveImagesAndPersistsOnlyServerSources() {
        List<Long> ids = List.of(1L, 2L, 3L, 4L, 5L);
        when(mapper.lockOwnedImages(7L, ids))
                .thenReturn(
                        ids.stream()
                                .map(id -> new Attachment(id.toString(), "截图.png", "image/png"))
                                .toList());
        service.save(
                new SaveRequest(date, List.of(new SaveRow(10L, 20L, "facebook", metrics(), ids))));
        ArgumentCaptor<DeliveryReportRecord> captor =
                ArgumentCaptor.forClass(DeliveryReportRecord.class);
        verify(mapper).upsert(captor.capture());
        assertThat(captor.getValue().getReporterId()).isEqualTo(7L);
        assertThat(captor.getValue().getAccountIdsJson()).isEqualTo("[\"account\"]");
        assertThat(captor.getValue().getMetricsJson()).doesNotContain("actualSpend");
        verify(mapper, times(5)).insertAttachment(eq(1L), anyLong(), anyInt());
    }

    @Test
    void rejectsMissingEnglishNameAndUnavailablePlatform() {
        when(mapper.findEnglishName(7L)).thenReturn(" ");
        assertThatThrownBy(() -> service.query(date)).hasMessageContaining("英文名称");
        verifyNoInteractions(provider);
        when(mapper.findEnglishName(7L)).thenReturn("Alice");
        when(provider.query(date, "Alice")).thenThrow(new DeliveryReportException("平台不可用"));
        assertThatThrownBy(
                        () ->
                                service.save(
                                        new SaveRequest(
                                                date,
                                                List.of(
                                                        new SaveRow(
                                                                10L,
                                                                20L,
                                                                "facebook",
                                                                metrics(),
                                                                List.of())))))
                .hasMessageContaining("平台不可用");
        verify(mapper, never()).upsert(any());
    }

    @Test
    void performanceUsesOwnSavedDatesAndCurrentDepartment() throws Exception {
        when(mapper.findReportDates(7L, date.minusDays(2), date)).thenReturn(List.of(date));
        when(mapper.findDepartmentName(7L)).thenReturn("投放部");
        when(mapper.findRecords(7L, date)).thenReturn(List.of(record()));
        PerformanceResult result = service.performance(date.minusDays(2), date);
        assertThat(result.departmentName()).isEqualTo("投放部");
        assertThat(result.days()).hasSize(1);
        assertThat(result.days().getFirst().rows()).hasSize(1).allMatch(Row::saved);
        assertThat(result.days().getFirst().reporterId()).isEqualTo("7");
        verify(provider, times(1)).query(date, "Alice");
    }

    @Test
    void performanceRejectsInvalidRangeAndUnauthenticatedAccess() {
        assertThatThrownBy(() -> service.performance(date, date.minusDays(1)))
                .hasMessageContaining("开始日期");
        verify(mapper, never()).findReportDates(any(), any(), any());
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.performance(date, date))
                .isInstanceOf(DeliveryReportException.class);
    }

    @Test
    void emptyPerformanceDoesNotReadPlatformAndDefaultsMissingDepartment() {
        when(mapper.findReportDates(7L, date, date)).thenReturn(List.of());
        PerformanceResult result = service.performance(date, date);
        assertThat(result.days()).isEmpty();
        assertThat(result.departmentName()).isEqualTo("未设置");
        verifyNoInteractions(provider);
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(strings = {"AM", "OPERATOR_LEADER", "ADMIN"})
    void privilegedRolesCanReadOtherReportersAndSummary(String role) throws Exception {
        var authorities =
                List.of(
                        new org.springframework.security.core.authority.SimpleGrantedAuthority(
                                "ROLE_" + role));
        var user = new CurrentUser(7L, "session", "管理员", authorities);
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, authorities));
        when(mapper.findReporters(8L)).thenReturn(List.of(new Reporter("8", "其他投手")));
        when(mapper.findReporters(null)).thenReturn(List.of(new Reporter("8", "其他投手")));
        when(mapper.findOperatorReporters(null)).thenReturn(List.of(new Reporter("8", "其他投手")));
        when(mapper.findReportDates(8L, date, date)).thenReturn(List.of(date));
        when(mapper.findDepartmentName(8L)).thenReturn("其他部门");
        when(mapper.findEnglishName(8L)).thenReturn("Bob");
        when(mapper.findReadEnglishName(8L)).thenReturn("Bob");
        when(provider.query(date, "Bob")).thenReturn(List.of(platform()));
        when(mapper.findRecords(8L, date)).thenReturn(List.of(record()));
        var other = record();
        other.setReporterId(8L);
        other.setReporterName("其他投手");
        other.setDepartmentName("其他部门");
        when(mapper.findReadRecords(
                        eq(8L), eq(date), eq(date), isNull(), isNull(), isNull(), isNull(), eq(0L)))
                .thenReturn(List.of(other));
        when(mapper.findReadRecords(
                        isNull(), eq(date), eq(date), isNull(), isNull(), isNull(), isNull(),
                        eq(0L)))
                .thenReturn(List.of(other));
        assertThat(service.reporters()).containsExactly(new Reporter("8", "其他投手"));
        var read = service.read(date, 8L);
        assertThat(read.getFirst().reporterId()).isEqualTo("8");
        assertThat(read.getFirst().departmentName()).isEqualTo("其他部门");
        assertThat(read.getFirst().rows()).allMatch(Row::saved);
        assertThat(service.performance(date, date, null).days()).hasSize(1);
        verify(mapper, never()).upsert(any());
    }

    @Test
    void ordinaryUserCannotOverrideReporterAndSummaryStaysOwn() {
        assertThat(service.reporters()).containsExactly(new Reporter("7", "投手"));
        assertThatThrownBy(() -> service.read(date, 8L)).hasMessageContaining("无权");
        assertThatThrownBy(() -> service.performance(date, date, 8L)).hasMessageContaining("无权");
        when(mapper.findReportDates(7L, date, date)).thenReturn(List.of());
        assertThat(service.read(date, null)).isEmpty();
        verify(mapper, never()).findReporters(any());
        verify(mapper, never()).findReportDates(eq(8L), any(), any());
    }

    @Test
    void similarlyNamedRoleDoesNotGrantAllAccess() {
        var authorities =
                List.of(
                        new org.springframework.security.core.authority.SimpleGrantedAuthority(
                                "ROLE_AM_ASSISTANT"));
        var user = new CurrentUser(7L, "session", "ADMIN", authorities);
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, authorities));
        assertThatThrownBy(() -> service.read(date, 8L)).hasMessageContaining("无权");
    }

    @Test
    void adminSaveStillUsesOwnIdentity() {
        var authorities =
                List.of(
                        new org.springframework.security.core.authority.SimpleGrantedAuthority(
                                "ROLE_ADMIN"));
        var user = new CurrentUser(7L, "session", "管理员", authorities);
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(user, null, authorities));
        service.save(
                new SaveRequest(
                        date, List.of(new SaveRow(10L, 20L, "facebook", metrics(), List.of()))));
        var captured = ArgumentCaptor.forClass(DeliveryReportRecord.class);
        verify(mapper).upsert(captured.capture());
        assertThat(captured.getValue().getReporterId()).isEqualTo(7L);
        verify(mapper).lockReporter(7L);
    }

    @Test
    void nonOperatorIsNotAddedToNavigationAsFallback() {
        when(mapper.findOperatorReporters(7L)).thenReturn(List.of());
        assertThat(service.reporters()).isEmpty();
        verify(mapper).findOperatorReporters(7L);
        verify(mapper, never()).findOperatorReporters(null);
    }

    @Test
    void pageBatchesSpendAndImagesAndPushesFiltersAndOffsetIntoMysql() throws Exception {
        when(mapper.countReadRecords(7L, date, date, "投", "Proj", "Line")).thenReturn(42L);
        when(mapper.findReadRecords(7L, date, date, "投", "Proj", "Line", 20, 20L))
                .thenReturn(List.of(record()));
        when(provider.querySpend(date, date, List.of("Alice")))
                .thenReturn(
                        List.of(
                                new SpendRow(
                                        date,
                                        "Alice",
                                        "Project",
                                        "Line",
                                        "facebook",
                                        new BigDecimal("100.12"))));
        when(mapper.findReadAttachments(List.of(1L)))
                .thenReturn(List.of(new ReportAttachment("1", "9", "截图", "image/png")));
        var result = service.page(date, date, null, 2, 20, "投", "Proj", "Line");
        assertThat(result.total()).isEqualTo(42L);
        assertThat(result.page()).isEqualTo(2);
        var row = result.days().getFirst().rows().getFirst();
        assertThat(row.actualSpend()).isEqualByComparingTo("100.12");
        assertThat(row.attachments()).hasSize(1);
        verify(provider, times(1)).querySpend(date, date, List.of("Alice"));
        verify(provider, never()).query(any(), anyString());
        verify(mapper, never()).findReporters(any());
        verify(mapper, never()).findRecords(any(), any());
        verify(mapper, never()).findAttachments(any());
    }

    @Test
    void statisticsAreUnpagedAndDoNotLoadAttachments() throws Exception {
        var second = record();
        second.setId(2L);
        second.setPlatform("google");
        when(mapper.findReadRecords(7L, date, date, "", "", "", null, 0L))
                .thenReturn(List.of(record(), second));
        when(provider.querySpend(date, date, List.of("Alice")))
                .thenReturn(
                        List.of(
                                new SpendRow(
                                        date,
                                        "Alice",
                                        "Project",
                                        "Line",
                                        "facebook",
                                        new BigDecimal("100.12"))));
        var result = service.stats(date, date, null, "", "", "");
        assertThat(result.count()).isEqualTo(2);
        assertThat(result.dailySpend()).isEqualByComparingTo("180.00");
        assertThat(result.actualSpend()).isEqualByComparingTo("100.12");
        verify(mapper, never()).findReadAttachments(anyList());
    }

    @Test
    void paginationAndStatisticsRejectCrossUserAccessAndInvalidPageSize() {
        assertThatThrownBy(() -> service.page(date, date, 8L, 1, 20, "", "", ""))
                .hasMessageContaining("无权");
        assertThatThrownBy(() -> service.stats(date, date, 8L, "", "", ""))
                .hasMessageContaining("无权");
        assertThatThrownBy(() -> service.page(date, date, null, 1, 101, "", "", ""))
                .hasMessageContaining("分页");
        assertThat(service.page(date, date, null, 1, 20, "", "", "").days()).isEmpty();
        verifyNoInteractions(provider);
    }

    @Test
    void rangePagePreservesDailyRowsAndStatisticsCoverBothBoundaryDates() throws Exception {
        LocalDate end = date.plusDays(1);
        var first = record();
        var second = record();
        second.setId(2L);
        second.setReportDate(end);
        when(mapper.countReadRecords(7L, date, end, "", "", "")).thenReturn(2L);
        when(mapper.findReadRecords(7L, date, end, "", "", "", 20, 0L))
                .thenReturn(List.of(second, first));
        when(mapper.findReadRecords(7L, date, end, "", "", "", null, 0L))
                .thenReturn(List.of(second, first));
        when(provider.querySpend(date, end, List.of("Alice")))
                .thenReturn(
                        List.of(
                                new SpendRow(
                                        date,
                                        "Alice",
                                        "Project",
                                        "Line",
                                        "facebook",
                                        new BigDecimal("10.12")),
                                new SpendRow(
                                        end,
                                        "Alice",
                                        "Project",
                                        "Line",
                                        "facebook",
                                        new BigDecimal("20.34"))));
        var page = service.page(date, end, null, 1, 20, "", "", "");
        assertThat(page.days()).extracting(Result::date).containsExactly(end, date);
        assertThat(page.days().getFirst().rows()).hasSize(1);
        assertThat(page.days().getFirst().rows().getFirst().actualSpend())
                .isEqualByComparingTo("20.34");
        var stats = service.stats(date, end, null, "", "", "");
        assertThat(stats.count()).isEqualTo(2);
        assertThat(stats.dailySpend()).isEqualByComparingTo("180.00");
        assertThat(stats.actualSpend()).isEqualByComparingTo("30.46");
    }

    @Test
    void rangePageAndStatsRejectReversedOrMissingDates() {
        assertThatThrownBy(() -> service.page(date, date.minusDays(1), null, 1, 20, "", "", ""))
                .hasMessageContaining("开始日期");
        assertThatThrownBy(() -> service.stats(null, date, null, "", "", ""))
                .hasMessageContaining("开始日期");
        verifyNoInteractions(provider);
    }

    private PlatformRow platform() {
        return new PlatformRow(
                "Project",
                "Line",
                "facebook",
                new BigDecimal("100"),
                1000,
                10,
                2,
                1,
                1,
                List.of("account"),
                List.of("campaign"));
    }

    private Metrics metrics() {
        return new Metrics(
                new BigDecimal("90"),
                1000L,
                10L,
                2L,
                1L,
                1L,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                "未设置",
                "");
    }

    private DeliveryReportRecord record() throws Exception {
        DeliveryReportRecord row = new DeliveryReportRecord();
        row.setReportDate(date);
        row.setReporterId(7L);
        row.setReporterName("投手");
        row.setDepartmentName("投放部");
        row.setReporterEnglishName("Alice");
        row.setId(1L);
        row.setProjectId(10L);
        row.setProjectName("Project");
        row.setAgencyLineId(20L);
        row.setAgencyLineName("Line");
        row.setPlatform("facebook");
        row.setMetricsJson(json.writeValueAsString(metrics()));
        row.setAccountIdsJson("[]");
        row.setCampaignIdsJson("[]");
        return row;
    }
}
