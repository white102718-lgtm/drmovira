package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class AssetApprovalQueryServiceTest {
    private DynamicAssetFlowMapper mapper;
    private AssetApprovalQueryService service;

    @BeforeEach
    void setUp() {
        mapper = mock(DynamicAssetFlowMapper.class);
        service =
                new AssetApprovalQueryService(
                        mapper, new AssetApprovalCcUserService(mapper, new ObjectMapper()));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                new CurrentUser(42L, "test-session", "测试用户", List.of()), null));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldMapFiltersAndReturnOnlyLightweightPageItems() {
        LocalDateTime createdAt = LocalDateTime.of(2026, 9, 15, 10, 0);
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", 1001L);
        row.put("applicationNo", "APP-1001");
        row.put("applicationDefinitionId", "8");
        row.put("assetType", "PIXEL");
        row.put("configCategory", "advertising");
        row.put("title", "像素申请");
        row.put("quantity", 2);
        row.put("reason", "投放使用");
        row.put("status", "PENDING");
        row.put("requesterId", 7L);
        row.put("requesterName", "申请人");
        row.put("approverId", 42L);
        row.put("approverName", "审批人");
        row.put("departmentId", "3");
        row.put("departmentName", "媒介部");
        row.put("projectName", "项目 A");
        row.put("ccUserIds", "9,10");
        row.put("createdAt", createdAt);
        row.put("updatedAt", createdAt);
        when(mapper.findApprovalPage(anyMap())).thenReturn(List.of(row));
        when(mapper.countApprovalPage(anyMap())).thenReturn(11L);
        when(mapper.findApprovalCcUsersByIds(List.of(9L, 10L)))
                .thenReturn(
                        List.of(
                                Map.of("id", 9L, "displayName", "抄送人甲", "status", 1),
                                Map.of("id", 10L, "displayName", "抄送人乙", "status", 0)));

        var result =
                service.page(
                        new AssetApprovalQueryService.Query(
                                "processed", 2, 10, " 项目 ", 8L, "pixel", 3L, 7L, "approved"));

        assertThat(result.hasMore()).isFalse();
        assertThat(result.items())
                .singleElement()
                .satisfies(
                        item -> {
                            assertThat(item.id()).isEqualTo("1001");
                            assertThat(item.departmentName()).isEqualTo("媒介部");
                            assertThat(item.projectName()).isEqualTo("项目 A");
                            assertThat(item.ccUsers())
                                    .extracting("id", "displayName", "active", "resolved")
                                    .containsExactly(
                                            org.assertj.core.groups.Tuple.tuple(
                                                    "9", "抄送人甲", true, true),
                                            org.assertj.core.groups.Tuple.tuple(
                                                    "10", "抄送人乙", false, true));
                        });
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        org.mockito.Mockito.verify(mapper).findApprovalPage(captor.capture());
        assertThat(captor.getValue())
                .containsEntry("userId", 42L)
                .containsEntry("queue", "processed")
                .containsEntry("offset", 10)
                .containsEntry("keyword", "项目")
                .containsEntry("assetType", "PIXEL")
                .containsEntry("decisionResult", "APPROVED");
    }

    @Test
    void shouldAllowFiveHundredApprovalItemsPerPage() {
        when(mapper.findApprovalPage(anyMap())).thenReturn(List.of());
        when(mapper.countApprovalPage(anyMap())).thenReturn(1001L);

        var result =
                service.page(
                        new AssetApprovalQueryService.Query(
                                "pending", 2, 500, null, null, null, null, null, null));

        assertThat(result.page()).isEqualTo(2);
        assertThat(result.pageSize()).isEqualTo(500);
        assertThat(result.hasMore()).isTrue();
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        org.mockito.Mockito.verify(mapper).findApprovalPage(captor.capture());
        assertThat(captor.getValue()).containsEntry("offset", 500).containsEntry("pageSize", 500);
    }

    @Test
    void shouldRejectApprovalPageSizeAboveFiveHundred() {
        var query =
                new AssetApprovalQueryService.Query(
                        "pending", 1, 501, null, null, null, null, null, null);

        assertThatThrownBy(() -> service.page(query))
                .isInstanceOf(com.adpulse.system.common.exception.BusinessException.class)
                .hasMessage("每页条数必须在 1 到 500 之间");
    }

    @Test
    void shouldKeepTenAsTheDefaultApprovalPageSize() {
        when(mapper.findApprovalPage(anyMap())).thenReturn(List.of());
        when(mapper.countApprovalPage(anyMap())).thenReturn(0L);

        var result =
                service.page(
                        new AssetApprovalQueryService.Query(
                                "pending", null, null, null, null, null, null, null, null));

        assertThat(result.page()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(10);
        ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
        org.mockito.Mockito.verify(mapper).findApprovalPage(captor.capture());
        assertThat(captor.getValue()).containsEntry("offset", 0).containsEntry("pageSize", 10);
    }

    @Test
    void shouldReturnUnfilteredQueueCountsAndVisibleOptions() {
        when(mapper.countApprovalPage(anyMap()))
                .thenAnswer(
                        invocation -> {
                            Map<String, Object> query = invocation.getArgument(0);
                            return switch ((String) query.get("queue")) {
                                case "pending" -> 5L;
                                case "handling" -> 4L;
                                case "processed" -> 3L;
                                case "copied" -> 2L;
                                default -> 1L;
                            };
                        });
        when(mapper.findApprovalDepartments(anyMap()))
                .thenReturn(List.of(Map.of("value", "3", "label", "媒介部")));
        when(mapper.findApprovalRequesters(anyMap()))
                .thenReturn(List.of(Map.of("value", "7", "label", "申请人")));

        var metadata = service.metadata();

        assertThat(metadata.queueCounts().pending()).isEqualTo(5);
        assertThat(metadata.queueCounts().initiated()).isEqualTo(1);
        assertThat(metadata.departments()).extracting("value").containsExactly("3");
        assertThat(metadata.requesters()).extracting("label").containsExactly("申请人");
    }
}
