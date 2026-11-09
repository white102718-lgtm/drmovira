package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AssetApprovalCcUserServiceTest {
    private DynamicAssetFlowMapper mapper;
    private AssetApprovalCcUserService service;

    @BeforeEach
    void setUp() {
        mapper = mock(DynamicAssetFlowMapper.class);
        service = new AssetApprovalCcUserService(mapper, new ObjectMapper());
    }

    @Test
    void resolvesMultipleUsersForOrdinaryApplicationAndKeepsDisabledUserName() {
        when(mapper.findApprovalCcUsersByIds(List.of(11L, 12L)))
                .thenReturn(
                        List.of(
                                Map.of("id", 11L, "displayName", "张三", "status", 1),
                                Map.of("id", 12L, "displayName", "李四", "status", 0)));

        List<AssetViews.ApprovalCcUser> users = service.resolveAll(List.of("11, 12,11")).getFirst();

        assertThat(users)
                .extracting("id", "displayName", "active", "resolved")
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("11", "张三", true, true),
                        org.assertj.core.groups.Tuple.tuple("12", "李四", false, true));
    }

    @Test
    @SuppressWarnings("unchecked")
    void enrichesMigratedHistoricalApplicationFromSnapshotIds() {
        when(mapper.findApprovalCcUsersByIds(List.of(21L)))
                .thenReturn(List.of(Map.of("id", 21L, "displayName", "历史抄送人", "status", 1)));
        Map<String, Object> application = new LinkedHashMap<>();
        application.put(
                "formData",
                new LinkedHashMap<>(
                        Map.of(
                                "_ccUserIds",
                                "[\"21\"]",
                                "_legacy",
                                Map.of("source", "legacy-payment"))));

        service.enrichApplications(List.of(application));

        List<AssetViews.ApprovalCcUser> users =
                (List<AssetViews.ApprovalCcUser>) application.get("ccUsers");
        assertThat(users)
                .singleElement()
                .satisfies(
                        user -> {
                            assertThat(user.id()).isEqualTo("21");
                            assertThat(user.displayName()).isEqualTo("历史抄送人");
                        });
    }

    @Test
    void returnsEmptyListWhenApplicationHasNoCcUsers() {
        assertThat(service.resolveAll(Arrays.asList("", null, List.of())))
                .containsExactly(List.of(), List.of(), List.of());
        verify(mapper, never()).findApprovalCcUsersByIds(org.mockito.ArgumentMatchers.anyList());
    }

    @Test
    void keepsUnresolvedHistoricalIdWithoutGuessingAName() {
        when(mapper.findApprovalCcUsersByIds(List.of(99L))).thenReturn(List.of());

        AssetViews.ApprovalCcUser user = service.resolveAll(List.of("99")).getFirst().getFirst();

        assertThat(user.id()).isEqualTo("99");
        assertThat(user.displayName()).isEqualTo("用户 99");
        assertThat(user.active()).isFalse();
        assertThat(user.resolved()).isFalse();
    }
}
