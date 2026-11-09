package com.adpulse.system.assetreturn.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.assetreturn.dto.AssetReturnRequests;
import com.adpulse.system.assetreturn.mapper.AssetReturnMapper;
import com.adpulse.system.assetreturn.model.AssetReturn;
import com.adpulse.system.assetreturn.model.ReturnableAsset;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

/** 资产回收状态流转与权限边界测试。 */
@ExtendWith(MockitoExtension.class)
class AssetReturnServiceTest {

    @Mock private AssetReturnMapper mapper;
    @InjectMocks private AssetReturnService service;

    @BeforeEach
    void setCurrentUser() {
        authenticate(7L, List.of());
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldCreateReturnForCurrentAssigneeAndMarkAssetPending() {
        ReturnableAsset asset = assignedAsset(7L);
        when(mapper.lockAsset(31L)).thenReturn(asset);
        doAnswer(
                        invocation -> {
                            AssetReturn value = invocation.getArgument(0);
                            value.setId(91L);
                            return 1;
                        })
                .when(mapper)
                .insertReturn(any(AssetReturn.class));
        when(mapper.markAssetReturnPending(31L, 7L)).thenReturn(1);
        AssetReturn persisted = new AssetReturn();
        persisted.setId(91L);
        persisted.setStatus("PENDING");
        when(mapper.findReturn(91L)).thenReturn(persisted);

        AssetReturn result = service.create(31L, new AssetReturnRequests.Create("项目阶段结束"));

        assertThat(result.getId()).isEqualTo(91L);
        verify(mapper).markAssetReturnPending(31L, 7L);
    }

    @Test
    void shouldRejectReturnForAnotherUsersAsset() {
        when(mapper.lockAsset(31L)).thenReturn(assignedAsset(8L));

        assertThatThrownBy(() -> service.create(31L, new AssetReturnRequests.Create("项目阶段结束")))
                .isInstanceOf(BusinessException.class)
                .hasMessage("只能回收分配给自己的资产");
    }

    @Test
    void shouldAllowManagerToCreateReturnForAnotherUser() {
        authenticate(7L, List.of(new SimpleGrantedAuthority(AssetReturnService.MANAGE_AUTHORITY)));
        when(mapper.lockAsset(31L)).thenReturn(assignedAsset(8L));
        doAnswer(
                        invocation -> {
                            AssetReturn value = invocation.getArgument(0);
                            value.setId(91L);
                            return 1;
                        })
                .when(mapper)
                .insertReturn(any(AssetReturn.class));
        when(mapper.markAssetReturnPending(31L, 7L)).thenReturn(1);
        when(mapper.findReturn(91L)).thenReturn(new AssetReturn());

        service.create(31L, new AssetReturnRequests.Create("资源管理员代回收"));

        verify(mapper).markAssetReturnPending(31L, 7L);
    }

    @Test
    void shouldCompleteReturnAndReleaseAssetAsAvailable() {
        AssetReturn pending = new AssetReturn();
        pending.setId(91L);
        pending.setAssetId(31L);
        pending.setStatus("PENDING");
        ReturnableAsset asset = assignedAsset(7L);
        asset.setStatus("RETURN_PENDING");
        when(mapper.lockReturn(91L)).thenReturn(pending);
        when(mapper.lockAsset(31L)).thenReturn(asset);
        when(mapper.completeReturn(91L, "AVAILABLE", 7L, "测试用户")).thenReturn(1);
        when(mapper.releaseAsset(31L, "AVAILABLE", 7L)).thenReturn(1);
        AssetReturn completed = new AssetReturn();
        completed.setId(91L);
        completed.setStatus("COMPLETED");
        completed.setOutcome("AVAILABLE");
        when(mapper.findReturn(91L)).thenReturn(completed);

        AssetReturn result = service.complete(91L, new AssetReturnRequests.Complete("available"));

        assertThat(result.getOutcome()).isEqualTo("AVAILABLE");
        verify(mapper).releaseAsset(31L, "AVAILABLE", 7L);
    }

    @Test
    void shouldNormalizeAssetTypeFiltersForPagedReturns() {
        when(mapper.countReturns(null, null, "PERSONAL", "fb")).thenReturn(0L);

        service.page(" ", null, "personal", "FB", 1, 20);

        verify(mapper).countReturns(null, null, "PERSONAL", "fb");
        verify(mapper).findReturns(null, null, "PERSONAL", "fb", 0, 20);
    }

    private ReturnableAsset assignedAsset(Long assigneeId) {
        ReturnableAsset asset = new ReturnableAsset();
        asset.setId(31L);
        asset.setAssetType("PERSONAL");
        asset.setAssetName("测试个号");
        asset.setAssetCode("account@example.com");
        asset.setProjectId("channel-1");
        asset.setProjectName("测试渠道");
        asset.setAssigneeId(assigneeId);
        asset.setAssigneeName("使用人");
        asset.setApplicationId(21L);
        asset.setStatus("ASSIGNED");
        return asset;
    }

    private void authenticate(Long userId, List<SimpleGrantedAuthority> authorities) {
        CurrentUser user = new CurrentUser(userId, "session", "测试用户", authorities);
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", authorities));
    }
}
