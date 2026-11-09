package com.adpulse.system.asset.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.adpulse.system.application.service.ApplicationDefinitionService;
import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.asset.service.AccountOpeningChannelAccountService;
import com.adpulse.system.asset.service.AssetApprovalCcUserService;
import com.adpulse.system.asset.service.AssetApprovalCommentService;
import com.adpulse.system.asset.service.AssetApprovalDecisionService;
import com.adpulse.system.asset.service.AssetApprovalPrincipalService;
import com.adpulse.system.asset.service.AssetApprovalQueryService;
import com.adpulse.system.asset.service.AssetApprovalTransferService;
import com.adpulse.system.asset.service.AssetService;
import com.adpulse.system.asset.service.DynamicFormReferenceService;
import com.adpulse.system.asset.service.PixelApplicationAssignmentService;
import com.adpulse.system.asset.service.SiteNotificationService;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.PostMapping;

/** 动态审批表单配置及业务数据校验测试。 */
class DynamicAssetFlowControllerTest {
    @Test
    void shouldAllowPixelApprovalConfigWithResourceAssignmentEnabled() {
        DynamicAssetFlowController controller = approvalConfigController("PIXEL");

        try {
            assertThatCode(() -> controller.saveConfig(pixelConfigWithResourceAssignment()))
                    .doesNotThrowAnyException();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void shouldAllowProjectClosureConfigWithDateRangeField() {
        DynamicAssetFlowController controller = approvalConfigController("PROJECT_CLOSURE");

        try {
            assertThatCode(() -> controller.saveConfig(projectClosureConfig("date-range")))
                    .doesNotThrowAnyException();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    void shouldRejectUnsupportedApprovalFormFieldType() {
        DynamicAssetFlowController controller = approvalConfigController("PROJECT_CLOSURE");

        try {
            assertThatThrownBy(() -> controller.saveConfig(projectClosureConfig("unknown-field")))
                    .isInstanceOf(BusinessException.class)
                    .hasMessage("不支持的表单控件类型：unknown-field");
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void shouldDecodeRequesterDepartmentFromJsonFormData() throws Exception {
        DynamicAssetFlowController controller =
                new DynamicAssetFlowController(
                        null,
                        new ObjectMapper(),
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
                        null);
        Map<String, Object> application = new LinkedHashMap<>();
        application.put(
                "formData",
                "{\"_requesterDepartmentId\":\"50\"," + "\"_requesterDepartmentName\":\"测试部门\"}");
        application.put("nodes", "[]");

        Method decode =
                DynamicAssetFlowController.class.getDeclaredMethod(
                        "decodeApplicationFields", Map.class);
        decode.setAccessible(true);
        Map<String, Object> decoded = (Map<String, Object>) decode.invoke(controller, application);

        assertThat(decoded.get("departmentId")).isEqualTo("50");
        assertThat(decoded.get("departmentName")).isEqualTo("测试部门");
        assertThat((Map<String, Object>) decoded.get("formData"))
                .containsEntry("_requesterDepartmentName", "测试部门");
    }

    @Test
    void shouldExposeBatchDecisionOnTheDynamicApprovalFlow() throws Exception {
        PostMapping mapping =
                DynamicAssetFlowController.class
                        .getMethod("batchDecide", AssetRequests.BatchDecision.class)
                        .getAnnotation(PostMapping.class);

        assertThat(mapping).isNotNull();
        assertThat(mapping.value()).containsExactly("/approvals/batch-decide");
    }

    @Test
    void shouldRequireInventoryAllocationForPixelProcessing() {
        assertThat(DynamicAssetFlowController.requiresAssetAllocation("PIXEL")).isTrue();
        assertThat(DynamicAssetFlowController.requiresAssetAllocation("BM")).isTrue();
    }

    @Test
    void shouldAcceptAnyNonEmptyNameAndIdValues() {
        assertThat(DynamicAssetFlowController.validPixelList("E2E验收BM关联:任意像素标识 ID_#-测试")).isTrue();
    }

    @Test
    void shouldAcceptMultiplePixelEntries() {
        assertThat(
                        DynamicAssetFlowController.validPixelList(
                                "网站像素：123456；应用像素:PIXEL-E2E-990000000001"))
                .isTrue();
    }

    @Test
    void shouldExposeAccountApprovalActorsAndOperationAmount() {
        DynamicAssetFlowMapper mapper = mock(DynamicAssetFlowMapper.class);
        LocalDateTime submittedAt = LocalDateTime.of(2026, 9, 15, 9, 0);
        LocalDateTime approvedAt = submittedAt.plusHours(1);
        Map<String, Object> applicationRow = new LinkedHashMap<>();
        applicationRow.put("id", 8L);
        applicationRow.put("applicationCode", "ACCOUNT_RECHARGE");
        applicationRow.put("title", "广告账户充值申请");
        applicationRow.put("status", "APPROVED");
        applicationRow.put("requesterName", "申请人");
        applicationRow.put("amount", new BigDecimal("200.00"));
        applicationRow.put("currency", "USD");
        applicationRow.put("createdAt", submittedAt);
        applicationRow.put("decidedAt", approvedAt);
        applicationRow.put(
                "formData",
                """
                {"accountIds":["100"],"accountNames":["测试账户 · 100"],
                 "rechargeAmount":200,"urgent":true,"quantity":2,"remark":"","_token":"REDACTED_REFERENCE_SECRET"}
                """);
        applicationRow.put(
                "formSchema",
                """
                [{"key":"group","label":"充值信息","type":"section"},
                 {"key":"accountIds","label":"广告账户","type":"multi-select","optionSource":"ad-accounts"},
                 {"key":"rechargeAmount","label":"充值金额","type":"number"},
                 {"key":"urgent","label":"加急","type":"switch"},
                 {"key":"quantity","label":"数量","type":"number"},
                 {"key":"remark","label":"备注","type":"textarea"}]
                """);
        when(mapper.findAccountLifecycleApplications("100")).thenReturn(List.of(applicationRow));
        when(mapper.findAccountLifecycleActions("100"))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id", 9L,
                                        "applicationId", 8L,
                                        "action", "APPROVED",
                                        "actorName", "审批人",
                                        "nodeName", "财务审批",
                                        "remark", "同意",
                                        "createdAt", approvedAt)));
        DynamicAssetFlowController controller = lifecycleController(mapper);

        var application = controller.accountLifecycleApplications("act_100").data().getFirst();

        assertThat(application.amount()).isEqualByComparingTo("200.00");
        assertThat(application.actions())
                .singleElement()
                .satisfies(action -> assertThat(action.actorName()).isEqualTo("审批人"));
        assertThat(application.formFields())
                .extracting(field -> field.key() + "=" + field.value())
                .containsExactly(
                        "accountIds=测试账户 · 100",
                        "rechargeAmount=USD 200.00",
                        "urgent=是",
                        "quantity=2");
        assertThat(application.formFields().getFirst().fullWidth()).isTrue();
    }

    @Test
    void shouldGracefullyIgnoreMalformedLifecycleFormSnapshot() {
        DynamicAssetFlowMapper mapper = mock(DynamicAssetFlowMapper.class);
        Map<String, Object> applicationRow = new LinkedHashMap<>();
        applicationRow.put("id", 9L);
        applicationRow.put("status", "APPROVED");
        applicationRow.put("createdAt", LocalDateTime.of(2026, 9, 15, 9, 0));
        applicationRow.put("formData", "{bad");
        applicationRow.put("formSchema", "[bad");
        when(mapper.findAccountLifecycleApplications("100")).thenReturn(List.of(applicationRow));
        when(mapper.findAccountLifecycleActions("100")).thenReturn(List.of());

        var application =
                lifecycleController(mapper).accountLifecycleApplications("100").data().getFirst();

        assertThat(application.formFields()).isEmpty();
    }

    @Test
    void shouldRejectEntriesWithoutSingleNameAndIdDelimiter() {
        assertThat(DynamicAssetFlowController.validPixelList("网站像素:PIXEL:E2E")).isFalse();
    }

    private DynamicAssetFlowController approvalConfigController(String assetType) {
        DynamicAssetFlowMapper mapper = mock(DynamicAssetFlowMapper.class);
        when(mapper.countActiveUser(1L)).thenReturn(1);
        when(mapper.findConfig(assetType))
                .thenReturn(
                        new LinkedHashMap<>(
                                Map.of(
                                        "id", 1L,
                                        "formSchema", "[]",
                                        "nodes", "[]",
                                        "settings", "{}",
                                        "enabled", 1,
                                        "category", "advertising")));
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                new CurrentUser(1L, "test-session", "测试用户", List.of()), null));
        return new DynamicAssetFlowController(
                mapper,
                new ObjectMapper(),
                mock(AssetApprovalDecisionService.class),
                mock(AssetApprovalPrincipalService.class),
                mock(AssetApprovalTransferService.class),
                mock(AssetApprovalQueryService.class),
                mock(AssetApprovalCcUserService.class),
                mock(AssetApprovalCommentService.class),
                mock(AssetService.class),
                mock(AccountOpeningChannelAccountService.class),
                mock(DynamicFormReferenceService.class),
                mock(PixelApplicationAssignmentService.class),
                mock(SiteNotificationService.class),
                mock(ApplicationDefinitionService.class),
                mock(SystemNotificationService.class));
    }

    private DynamicAssetFlowController lifecycleController(DynamicAssetFlowMapper mapper) {
        return new DynamicAssetFlowController(
                mapper,
                new ObjectMapper(),
                mock(AssetApprovalDecisionService.class),
                mock(AssetApprovalPrincipalService.class),
                mock(AssetApprovalTransferService.class),
                mock(AssetApprovalQueryService.class),
                mock(AssetApprovalCcUserService.class),
                mock(AssetApprovalCommentService.class),
                mock(AssetService.class),
                mock(AccountOpeningChannelAccountService.class),
                mock(DynamicFormReferenceService.class),
                mock(PixelApplicationAssignmentService.class),
                mock(SiteNotificationService.class),
                mock(ApplicationDefinitionService.class),
                mock(SystemNotificationService.class));
    }

    private Map<String, Object> projectClosureConfig(String settlementPeriodType) {
        Map<String, Object> node =
                new LinkedHashMap<>(
                        Map.of("name", "业务负责人审批", "approverId", 1L, "approverName", "超级管理员"));
        return new LinkedHashMap<>(
                Map.of(
                        "assetType",
                        "PROJECT_CLOSURE",
                        "category",
                        "advertising",
                        "name",
                        "项目结项审批",
                        "handlerId",
                        "1",
                        "handlerName",
                        "系统管理员",
                        "formSchema",
                        List.of(
                                Map.of(
                                        "key",
                                        "settlementPeriod",
                                        "type",
                                        settlementPeriodType,
                                        "label",
                                        "结算周期",
                                        "required",
                                        true)),
                        "nodes",
                        List.of(node)));
    }

    private Map<String, Object> pixelConfigWithResourceAssignment() {
        Map<String, Object> node =
                new LinkedHashMap<>(
                        Map.of("name", "业务负责人审批", "approverId", 1L, "approverName", "超级管理员"));
        return new LinkedHashMap<>(
                Map.of(
                        "assetType",
                        "PIXEL",
                        "category",
                        "advertising",
                        "name",
                        "像素绑户申请",
                        "handlerId",
                        "1",
                        "handlerName",
                        "系统管理员",
                        "formSchema",
                        List.of(Map.of("key", "pixelNames", "type", "textarea", "label", "像素")),
                        "nodes",
                        List.of(node),
                        "settings",
                        Map.of(
                                "handlerAction",
                                Map.of(
                                        "resourceAssignment",
                                        Map.of(
                                                "enabled", true,
                                                "assetTypeSource", "application",
                                                "quantityFieldKey", "quantity")))));
    }
}
