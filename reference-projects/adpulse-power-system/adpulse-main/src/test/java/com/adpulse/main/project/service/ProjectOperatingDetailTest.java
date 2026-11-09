package com.adpulse.main.project.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.adpulse.main.project.dto.ProjectRequests.AgencyLineStatusChange;
import com.adpulse.main.project.dto.ProjectViews.CompletedTask;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.AgencyLine;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.safeheron.service.SafeheronWalletService;
import com.adpulse.system.common.security.CurrentUser;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

/** 项目业务状态、只读任务摘要及经营占位口径测试。 */
@ExtendWith(MockitoExtension.class)
class ProjectOperatingDetailTest {
    @Mock ProjectMapper mapper;
    @Mock SafeheronWalletService walletService;
    @Mock ProjectSpendQueryProvider spendQueryProvider;
    ProjectService service;

    @BeforeEach
    void setUp() {
        service = new ProjectService(mapper, walletService, spendQueryProvider);
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                new CurrentUser(9L, "session", "操作人", List.of()), "", List.of()));
    }

    @AfterEach
    void cleanUp() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void changesStatusWithoutChangingAdConfiguration() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        when(mapper.findAgencyLine(2L)).thenReturn(line(1L));
        when(mapper.updateAgencyLineStatus(2L, 1L, "stopped", 9L)).thenReturn(1);
        service.changeAgencyLineStatus(
                1L, new AgencyLineStatusChange(List.of("2", "2"), "stopped"));
        verify(mapper, times(1)).updateAgencyLineStatus(2L, 1L, "stopped", 9L);
        verify(mapper, never()).updateAgencyLine(any());
    }

    @Test
    void rejectsOtherProjectsBeforeAnyWrite() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        when(mapper.findAgencyLine(2L)).thenReturn(line(1L));
        when(mapper.findAgencyLine(3L)).thenReturn(line(8L));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L,
                                        new AgencyLineStatusChange(List.of("2", "3"), "stopped")))
                .hasMessageContaining("不属于");
        verify(mapper, never()).updateAgencyLineStatus(any(), any(), any(), any());
    }

    @Test
    void rejectsEndedProject() {
        when(mapper.findProject(1L)).thenReturn(project("ended"));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L, new AgencyLineStatusChange(List.of("2"), "stopped")))
                .hasMessageContaining("结束或归档");
    }

    @Test
    void rejectsInvalidStatusAndSelection() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L, new AgencyLineStatusChange(List.of("2"), "paused")))
                .hasMessageContaining("状态不合法");
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L, new AgencyLineStatusChange(List.of(), "active")))
                .hasMessageContaining("1至100");
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L,
                                        new AgencyLineStatusChange(List.of("invalid"), "active")))
                .hasMessageContaining("格式不正确");
    }

    @Test
    void rejectsConcurrentUnbinding() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        when(mapper.findAgencyLine(2L)).thenReturn(line(1L));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L, new AgencyLineStatusChange(List.of("2"), "active")))
                .hasMessageContaining("归属已变化");
    }

    @Test
    void returnsProjectWideTasksWithDorisSpend() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        when(spendQueryProvider.totalSpend("测试项目")).thenReturn(new BigDecimal("123.4567"));
        var tasks =
                List.of(
                        new CompletedTask(
                                "12", "TASK-12", "素材交付", "material", "其他成员", LocalDateTime.now()));
        when(mapper.findCompletedProjectTasks(1L, 0, 10)).thenReturn(tasks);
        when(mapper.countProjectTasks(1L, true)).thenReturn(1);
        when(mapper.countProjectTasks(1L, false)).thenReturn(3);
        var overview = service.operatingOverview(1L);
        assertThat(overview.completedTasks()).containsExactlyElementsOf(tasks);
        assertThat(overview.totalTaskCount()).isEqualTo(3);
        assertThat(overview.actualSpend()).isEqualByComparingTo("123.4567");
        assertThat(overview.dataQualityStatus()).isEqualTo("complete");
        assertThat(overview.settledAmount()).isEqualByComparingTo(BigDecimal.ZERO);
        assertThat(overview.metricCutoff()).isEmpty();
    }

    @Test
    void boundsTaskPaginationAndChecksProjectExists() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        var result = service.completedTasks(1L, -1, 1000);
        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(100);
        verify(mapper).findCompletedProjectTasks(1L, 0, 100);
        assertThatThrownBy(() -> service.completedTasks(2L, 1, 10)).hasMessageContaining("不存在");
    }

    @Test
    void aggregatesCompletedClosuresByCurrencyWithoutRoundingOrConversion() {
        when(mapper.findProject(1L)).thenReturn(project("active"));
        when(mapper.findClosureSettlements(1L))
                .thenReturn(
                        List.of(
                                new com.adpulse.main.project.dto.ProjectViews.ClosureSettlement(
                                        "USD - 美元", "0.1"),
                                new com.adpulse.main.project.dto.ProjectViews.ClosureSettlement(
                                        "USD", "0.2"),
                                new com.adpulse.main.project.dto.ProjectViews.ClosureSettlement(
                                        "CNY - 人民币", "100"),
                                new com.adpulse.main.project.dto.ProjectViews.ClosureSettlement(
                                        "JPY - 日元", "200")));
        var overview = service.operatingOverview(1L);
        assertThat(overview.settledAmounts())
                .containsExactly(
                        new com.adpulse.main.project.dto.ProjectViews.SettledAmount(
                                "CNY", new BigDecimal("100")),
                        new com.adpulse.main.project.dto.ProjectViews.SettledAmount(
                                "JPY", new BigDecimal("200")),
                        new com.adpulse.main.project.dto.ProjectViews.SettledAmount(
                                "USD", new BigDecimal("0.3")));
        assertThat(overview.settledAmount()).isEqualByComparingTo("0.3");
        assertThat(ProjectService.summarizeSettlements(List.of())).isEmpty();
    }

    @Test
    void rejectsInvalidClosureFieldsInsteadOfSilentlyUndercounting() {
        for (String amount : new String[] {null, "invalid", "-1"}) {
            assertThatThrownBy(
                            () ->
                                    ProjectService.summarizeSettlements(
                                            List.of(
                                                    new com.adpulse.main.project.dto.ProjectViews
                                                            .ClosureSettlement("USD", amount))))
                    .hasMessageContaining("金额无效");
        }
        assertThatThrownBy(
                        () ->
                                ProjectService.summarizeSettlements(
                                        List.of(
                                                new com.adpulse.main.project.dto.ProjectViews
                                                        .ClosureSettlement(null, "10"))))
                .hasMessageContaining("币种");
    }

    @Test
    void rejectsUnauthenticatedReadAndWrite() {
        SecurityContextHolder.clearContext();
        assertThatThrownBy(() -> service.operatingOverview(1L)).hasMessageContaining("未认证");
        assertThatThrownBy(() -> service.completedTasks(1L, 1, 10)).hasMessageContaining("未认证");
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatus(
                                        1L, new AgencyLineStatusChange(List.of("2"), "active")))
                .hasMessageContaining("未认证");
        verifyNoInteractions(mapper);
    }

    @Test
    void changesUnboundLineStatusWithoutOtherFields() {
        when(mapper.findAgencyLine(2L)).thenReturn(line(null));
        when(mapper.updateAgencyLineStatus(2L, null, "active", 9L)).thenReturn(1);
        service.changeAgencyLineStatuses(new AgencyLineStatusChange(List.of("2", "2"), "active"));
        verify(mapper, times(1)).updateAgencyLineStatus(2L, null, "active", 9L);
        verify(mapper, never()).updateAgencyLine(any());
    }

    @Test
    void rejectsClosedProjectBeforeBatchWrite() {
        when(mapper.findAgencyLine(2L)).thenReturn(line(1L));
        when(mapper.findProject(1L)).thenReturn(project("archived"));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatuses(
                                        new AgencyLineStatusChange(List.of("2"), "stopped")))
                .isInstanceOf(RuntimeException.class);
        verify(mapper, never()).updateAgencyLineStatus(any(), any(), any(), any());
    }

    @Test
    void rejectsInvalidGlobalStatusAndEmptyBatch() {
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatuses(
                                        new AgencyLineStatusChange(List.of("2"), "invalid")))
                .hasMessageContaining("状态不合法");
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineStatuses(
                                        new AgencyLineStatusChange(List.of(), "active")))
                .hasMessageContaining("1至100");
        verifyNoInteractions(mapper);
    }

    @Test
    void optimizerClearOnlyWritesOptimizerColumns() {
        when(mapper.findAgencyLine(2L)).thenReturn(line(null));
        when(mapper.updateAgencyLineOptimizer(any())).thenReturn(1);
        service.changeAgencyLineOptimizer(
                2L,
                new com.adpulse.main.project.dto.ProjectRequests.AgencyLineOptimizerChange(null));
        verify(mapper)
                .updateAgencyLineOptimizer(
                        argThat(
                                value ->
                                        value.getOptimizerId() == null
                                                && value.getOptimizerName() == null));
        verify(mapper, never()).updateAgencyLine(any());
    }

    @Test
    void optimizerSelectionUsesCanonicalUserName() {
        when(mapper.findAgencyLine(2L)).thenReturn(line(null));
        when(mapper.findUserReference(7L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(7L, "投手甲", 1));
        when(mapper.updateAgencyLineOptimizer(any())).thenReturn(1);
        service.changeAgencyLineOptimizer(
                2L,
                new com.adpulse.main.project.dto.ProjectRequests.AgencyLineOptimizerChange("7"));
        verify(mapper)
                .updateAgencyLineOptimizer(
                        argThat(
                                value ->
                                        Long.valueOf(7).equals(value.getOptimizerId())
                                                && "投手甲".equals(value.getOptimizerName())));
        verify(mapper, never()).updateAgencyLine(any());
    }

    @Test
    void optimizerSelectionRejectsDisabledUser() {
        when(mapper.findAgencyLine(2L)).thenReturn(line(null));
        when(mapper.findUserReference(7L))
                .thenReturn(new com.adpulse.main.project.model.ProjectUserReference(7L, "停用人员", 0));
        assertThatThrownBy(
                        () ->
                                service.changeAgencyLineOptimizer(
                                        2L,
                                        new com.adpulse.main.project.dto.ProjectRequests
                                                .AgencyLineOptimizerChange("7")))
                .hasMessageContaining("不可新分配停用人员");
        verify(mapper, never()).updateAgencyLineOptimizer(any());
    }

    private Project project(String status) {
        Project project = new Project();
        project.setId(1L);
        project.setProjectName("测试项目");
        project.setStatus(status);
        project.setProductInfo("产品信息");
        project.setProjectCode("P1");
        return project;
    }

    private AgencyLine line(Long projectId) {
        AgencyLine line = new AgencyLine();
        line.setId(2L);
        line.setProjectId(projectId);
        return line;
    }
}
