package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/** 动态表单系统下拉引用与名称快照测试。 */
@ExtendWith(MockitoExtension.class)
class DynamicFormReferenceServiceTest {
    @Mock private DynamicAssetFlowMapper flowMapper;
    private DynamicFormReferenceService service;

    @BeforeEach
    void setUp() {
        service = new DynamicFormReferenceService(flowMapper);
    }

    @Test
    void shouldIgnoreSectionNodes() {
        Map<String, Object> data = new LinkedHashMap<>();

        service.enrichSystemOptionSnapshots(
                List.of(Map.of("key", "sectionOwnership", "label", "申请归属", "type", "section")),
                data);

        assertThat(data).isEmpty();
        verifyNoInteractions(flowMapper);
    }

    @Test
    void shouldReplaceForgedChannelNameWithDatabaseSnapshot() {
        when(flowMapper.findActiveReferenceLabels("channels", 12L)).thenReturn(List.of("测试渠道"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("channelId", "12");
        data.put("channelName", "伪造名称");

        service.enrichSystemOptionSnapshots(
                List.of(
                        Map.of(
                                "key",
                                "channelId",
                                "label",
                                "所属渠道",
                                "type",
                                "select",
                                "optionSource",
                                "channels")),
                data);

        assertThat(data.get("channelName")).isEqualTo("测试渠道");
    }

    @Test
    void shouldResolvePixelUsageTeamFromSelectedDepartment() {
        when(flowMapper.findActiveReferenceLabels("departments", 18L)).thenReturn(List.of("投放一组"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("usageTeamId", "18");

        service.enrichSystemOptionSnapshots(
                List.of(
                        Map.of(
                                "key",
                                "usageTeamId",
                                "label",
                                "使用团队",
                                "type",
                                "select",
                                "optionSource",
                                "departments")),
                data);

        assertThat(data.get("usageTeamName")).isEqualTo("投放一组");
    }

    @Test
    void shouldRejectInactiveSystemOption() {
        when(flowMapper.findActiveReferenceLabels("departments", 99L)).thenReturn(List.of());
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("departmentId", "99");

        assertThatThrownBy(
                        () ->
                                service.enrichSystemOptionSnapshots(
                                        List.of(
                                                Map.of(
                                                        "key",
                                                        "departmentId",
                                                        "label",
                                                        "所属部门",
                                                        "type",
                                                        "select",
                                                        "optionSource",
                                                        "departments")),
                                        data))
                .isInstanceOf(BusinessException.class)
                .hasMessage("所属部门包含已停用或不存在的选项，请重新选择");
    }

    @Test
    void shouldValidateSystemAdAccountsAndWriteNameSnapshots() {
        when(flowMapper.findActiveAccountLabels("790000000004001"))
                .thenReturn(List.of("Meta 主投账户"));
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("accountIds", List.of("act_790000000004001"));

        service.enrichSystemOptionSnapshots(
                List.of(
                        Map.of(
                                "key",
                                "accountIds",
                                "label",
                                "广告账户",
                                "type",
                                "multi-select",
                                "optionSource",
                                "ad-accounts")),
                data);

        assertThat(data.get("accountIds")).isEqualTo(List.of("790000000004001"));
        assertThat(data.get("accountNames")).isEqualTo(List.of("Meta 主投账户"));
    }

    @Test
    void shouldUseMpowerSnapshotWhenAccountIsNotInLocalMirror() {
        when(flowMapper.findActiveAccountLabels("871240007")).thenReturn(List.of());
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("accountIds", List.of("871240007"));
        data.put("accountNames", List.of("MP014-BM5-林媒介-SG-260810-01 · act_871240007 · 企业户"));

        service.enrichSystemOptionSnapshots(
                List.of(
                        Map.of(
                                "key",
                                "accountIds",
                                "label",
                                "广告账户",
                                "type",
                                "multi-select",
                                "optionSource",
                                "ad-accounts")),
                data);

        assertThat(data.get("accountIds")).isEqualTo(List.of("871240007"));
        assertThat(data.get("accountNames"))
                .isEqualTo(List.of("MP014-BM5-林媒介-SG-260810-01 · act_871240007 · 企业户"));
    }

    @Test
    void shouldRejectMalformedSystemAdAccountIdBeforeDatabaseLookup() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("accountIds", List.of("act_invalid"));

        assertThatThrownBy(
                        () ->
                                service.enrichSystemOptionSnapshots(
                                        List.of(
                                                Map.of(
                                                        "key",
                                                        "accountIds",
                                                        "label",
                                                        "广告账户",
                                                        "type",
                                                        "multi-select",
                                                        "optionSource",
                                                        "ad-accounts")),
                                        data))
                .isInstanceOf(BusinessException.class)
                .hasMessage("广告账户包含无效选项，请重新选择");
        verifyNoInteractions(flowMapper);
    }
}
