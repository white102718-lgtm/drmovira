package com.adpulse.system.asset.controller;

import com.adpulse.system.application.dto.ApplicationDefinitionView;
import com.adpulse.system.application.service.ApplicationDefinitionService;
import com.adpulse.system.asset.dto.AssetRequests;
import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.asset.model.MediaAsset;
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
import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.notification.dto.NotificationMessage;
import com.adpulse.system.notification.dto.NotificationRecipients;
import com.adpulse.system.notification.service.SystemNotificationService;
import com.adpulse.system.operationlog.audit.OperationAudit;
import com.adpulse.system.operationlog.audit.OperationType;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** Dynamic form, multi-node approval and in-app notification endpoints. */
@RestController
@RequestMapping("/asset-flow-v2")
public class DynamicAssetFlowController {
    private static final Set<String> INVENTORY_TYPES =
            Set.of(
                    "AD_ACCOUNT",
                    "PERSONAL",
                    "BM",
                    "PIXEL",
                    "TG",
                    "PAGE",
                    "COMPUTER",
                    "MOBILE",
                    "STATIC_IP",
                    "EMAIL");
    private static final Set<String> CATEGORIES =
            Set.of("advertising", "office", "finance", "social");
    private static final Map<String, List<String>> LEGACY_ACCOUNT_FIELD_APPLICATIONS =
            Map.of(
                    "amount", List.of("ACCOUNT_RECHARGE", "ACCOUNT_DEDUCTION"),
                    "applyReason", List.of("ACCOUNT_ACTIVE_CLEAR", "ACCOUNT_ACTIVE_CLEAR_RECYCLE"),
                    "originalAuthAccount", List.of("ACCOUNT_REBIND"),
                    "authAccount", List.of("ACCOUNT_UNBIND", "ACCOUNT_REBIND"),
                    "remark",
                            List.of(
                                    "ACCOUNT_ACTIVE_CLEAR",
                                    "ACCOUNT_ACTIVE_CLEAR_RECYCLE",
                                    "ACCOUNT_RECYCLE"));
    private final DynamicAssetFlowMapper flowMapper;
    private final ObjectMapper json;
    private final AssetApprovalDecisionService decisionService;
    private final AssetApprovalPrincipalService principalService;
    private final AssetApprovalTransferService transferService;
    private final AssetApprovalQueryService approvalQueryService;
    private final AssetApprovalCcUserService ccUserService;
    private final AssetApprovalCommentService commentService;
    private final AssetService assetService;
    private final AccountOpeningChannelAccountService channelAccountService;
    private final DynamicFormReferenceService referenceService;
    private final PixelApplicationAssignmentService pixelAssignmentService;
    private final SiteNotificationService notificationService;
    private final ApplicationDefinitionService applicationDefinitionService;
    private final SystemNotificationService deliveryNotificationService;

    public DynamicAssetFlowController(
            DynamicAssetFlowMapper flowMapper,
            ObjectMapper json,
            AssetApprovalDecisionService decisionService,
            AssetApprovalPrincipalService principalService,
            AssetApprovalTransferService transferService,
            AssetApprovalQueryService approvalQueryService,
            AssetApprovalCcUserService ccUserService,
            AssetApprovalCommentService commentService,
            AssetService assetService,
            AccountOpeningChannelAccountService channelAccountService,
            DynamicFormReferenceService referenceService,
            PixelApplicationAssignmentService pixelAssignmentService,
            SiteNotificationService notificationService,
            ApplicationDefinitionService applicationDefinitionService,
            SystemNotificationService deliveryNotificationService) {
        this.flowMapper = flowMapper;
        this.json = json;
        this.decisionService = decisionService;
        this.principalService = principalService;
        this.transferService = transferService;
        this.approvalQueryService = approvalQueryService;
        this.ccUserService = ccUserService;
        this.commentService = commentService;
        this.assetService = assetService;
        this.channelAccountService = channelAccountService;
        this.referenceService = referenceService;
        this.pixelAssignmentService = pixelAssignmentService;
        this.notificationService = notificationService;
        this.applicationDefinitionService = applicationDefinitionService;
        this.deliveryNotificationService = deliveryNotificationService;
    }

    @GetMapping("/approval-configs")
    public ApiResponse<List<Map<String, Object>>> configs() {
        return ApiResponse.success(queryConfigs(false));
    }

    /** 返回审批管理页使用的完整配置，包括已停用和仅管理员可见的配置。 */
    @GetMapping("/approval-configs/manage")
    public ApiResponse<List<Map<String, Object>>> managedConfigs() {
        return ApiResponse.success(queryConfigs(true));
    }

    /** 申请人选择像素时使用的脱敏分页查询，仅返回当前可分配库存。 */
    @PostMapping("/selectable-pixels/search")
    public ApiResponse<Map<String, Object>> selectablePixels(
            @RequestBody Map<String, Object> body) {
        int page = Math.max(1, intValue(body.get("page"), 1));
        int pageSize = Math.min(100, Math.max(1, intValue(body.get("pageSize"), 10)));
        Map<String, Object> requestedFilters = map(body.get("filterValues"));
        Set<String> allowedKeys =
                Set.of(
                        "id",
                        "details.pixelId",
                        "details.pixelName",
                        "details.bmId",
                        "details.bmName",
                        "details.pixelTestCode",
                        "createdAt",
                        "note");
        Map<String, List<String>> filterValues = new LinkedHashMap<>();
        requestedFilters.forEach(
                (key, value) -> {
                    if (!allowedKeys.contains(key)) return;
                    List<String> values =
                            value instanceof List<?>
                                    ? stringList(value)
                                    : value == null ? List.of() : List.of(value.toString().trim());
                    if (!values.isEmpty()) filterValues.put(key, values);
                });
        filterValues.put("status", List.of("available"));
        Map<String, String> controls = new LinkedHashMap<>();
        allowedKeys.forEach(key -> controls.put(key, "text"));
        controls.put("id", "select");
        controls.put("details.pixelId", "select");
        controls.put("details.bmId", "select");
        controls.put("createdAt", "date");
        controls.put("status", "select");

        AssetViews.AssetPage result =
                assetService.searchAssets(
                        new AssetRequests.AssetSearch(
                                "PIXEL",
                                "pixel",
                                "",
                                Map.of(),
                                filterValues,
                                controls,
                                page,
                                pageSize,
                                false));
        List<Map<String, Object>> items =
                result.items().stream().map(this::selectablePixelView).toList();
        return ApiResponse.success(
                params(
                        "items", items,
                        "total", result.total(),
                        "page", result.page(),
                        "pageSize", result.pageSize()));
    }

    @PutMapping("/approval-configs")
    @Transactional
    public ApiResponse<Map<String, Object>> saveConfig(@RequestBody Map<String, Object> body) {
        String type = configKey(required(body, "assetType"));
        String requestedCategory = required(body, "category");
        if (!CATEGORIES.contains(requestedCategory)) throw validation("不支持的申请分类");
        String name = required(body, "name");
        List<Map<String, Object>> fields = list(body.get("formSchema"));
        List<Map<String, Object>> nodes = list(body.get("nodes"));
        validateTemplate(fields, nodes);
        Map<String, Object> settings = new LinkedHashMap<>(map(body.get("settings")));
        String completionMode = Objects.toString(settings.get("completionMode"), "handler").trim();
        if (!Set.of("handler", PixelApplicationAssignmentService.COMPLETION_MODE)
                .contains(completionMode)) {
            throw validation("不支持的流程完成方式");
        }
        boolean pixelAutoAssignment =
                PixelApplicationAssignmentService.COMPLETION_MODE.equals(completionMode);
        Map<String, Object> handlerAction = map(settings.get("handlerAction"));
        String handlerSource = Objects.toString(body.get("handlerSource"), "fixed-user").trim();
        String handlerApprovalNodeId =
                Objects.toString(body.get("handlerApprovalNodeId"), "").trim();
        long handlerId = number(body.get("handlerId"));
        String handlerName = Objects.toString(body.get("handlerName"), "").trim();
        if (pixelAutoAssignment) {
            if (!"manual".equals(Objects.toString(settings.get("approvalType"), "manual"))) {
                throw validation("像素自动分配流程仅支持人工审批");
            }
            boolean hasPixelSelector =
                    fields.stream()
                            .anyMatch(
                                    field ->
                                            PixelApplicationAssignmentService.PIXEL_IDS_KEY.equals(
                                                            field.get("key"))
                                                    && "pixel-selector".equals(field.get("type")));
            if (!hasPixelSelector) throw validation("像素自动分配流程必须配置像素选择字段");
            settings.remove("handlerAction");
            settings.remove("handlerSource");
            settings.remove("handlerApprovalNodeId");
            handlerAction = Map.of();
            handlerSource = "fixed-user";
            handlerApprovalNodeId = "";
            handlerId = 0;
            handlerName = "";
            nodes.forEach(
                    node -> {
                        node.remove("handlerId");
                        node.remove("handlerName");
                        node.remove("handlerSource");
                        node.remove("handlerApprovalNodeId");
                        node.remove("handlerAction");
                        node.remove("handlerIsApprover");
                    });
        } else {
            validateHandlerAction(type, handlerAction);
            if (!"approval-node".equals(handlerSource) && !"fixed-user".equals(handlerSource)) {
                throw validation("不支持的办理人来源");
            }
            boolean resolvedWhenApproved = false;
            if ("approval-node".equals(handlerSource)) {
                String selectedApprovalNodeId = handlerApprovalNodeId;
                Map<String, Object> sourceNode =
                        nodes.stream()
                                .filter(
                                        node ->
                                                selectedApprovalNodeId.equals(
                                                        Objects.toString(node.get("id"), "")))
                                .findFirst()
                                .orElseThrow(() -> validation("请选择有效的关联审批节点"));
                String approverType = Objects.toString(sourceNode.get("approverType"), "USERS");
                if (!Set.of("USERS", "ROLES", "DEPARTMENTS").contains(approverType)) {
                    throw validation("关联审批节点类型不受支持");
                }
                resolvedWhenApproved = !"USERS".equals(approverType);
                if (resolvedWhenApproved
                        && !"manual"
                                .equals(Objects.toString(settings.get("approvalType"), "manual"))) {
                    throw validation("自动审批流程无法关联角色或部门审批节点作为办理人来源");
                }
                if ("USERS".equals(approverType)) {
                    handlerId = number(sourceNode.get("approverId"));
                    handlerName = Objects.toString(sourceNode.get("approverName"), "").trim();
                    if (handlerId <= 0 || handlerName.isBlank()) {
                        throw validation("关联审批节点必须配置具体审批人");
                    }
                } else {
                    handlerId = 0;
                    handlerName = "";
                }
            } else if (handlerName.isBlank()) {
                throw validation("流程处理人名称不能为空");
            }
            if (!resolvedWhenApproved && (handlerId <= 0 || !activeUser(handlerId))) {
                throw validation("流程处理人不存在或已停用");
            }
            settings.put("handlerSource", handlerSource);
            settings.put("handlerApprovalNodeId", handlerApprovalNodeId);
            long resolvedHandlerId = handlerId;
            String resolvedHandlerName = handlerName;
            String resolvedHandlerSource = handlerSource;
            String resolvedHandlerApprovalNodeId = handlerApprovalNodeId;
            Map<String, Object> resolvedHandlerAction = handlerAction;
            nodes.forEach(
                    node -> {
                        node.put("handlerId", resolvedHandlerId);
                        node.put("handlerName", resolvedHandlerName);
                        node.put("handlerSource", resolvedHandlerSource);
                        node.put("handlerApprovalNodeId", resolvedHandlerApprovalNodeId);
                        node.put("handlerAction", resolvedHandlerAction);
                        node.remove("handlerIsApprover");
                    });
        }
        Map<String, Object> first = nodes.get(0);
        long operator = SecurityContextHelper.currentUserId();
        boolean enabled = !Boolean.FALSE.equals(body.get("enabled"));
        flowMapper.upsertApprovalConfig(
                params(
                        "assetType",
                        type,
                        "category",
                        requestedCategory,
                        "approverId",
                        number(first.get("approverId")),
                        "approverName",
                        required(first, "approverName"),
                        "ccUserIds",
                        Objects.toString(body.get("ccUserIds"), ""),
                        "name",
                        name,
                        "description",
                        Objects.toString(body.get("description"), ""),
                        "icon",
                        Objects.toString(body.get("icon"), "lucide:workflow"),
                        "visibility",
                        "admins".equals(body.get("visibility")) ? "admins" : "all",
                        "settings",
                        stringify(settings),
                        "sortOrder",
                        intValue(body.get("sortOrder"), 0),
                        "formSchema",
                        stringify(fields),
                        "nodes",
                        stringify(nodes),
                        "enabled",
                        enabled ? 1 : 0,
                        "operatorId",
                        operator));
        Map<String, Object> savedConfig = findConfig(type);
        if (body.containsKey("applicationDefinitionIds")) {
            applicationDefinitionService.replaceApprovalConfigApplications(
                    number(savedConfig.get("id")),
                    applicationDefinitionIds(body.get("applicationDefinitionIds")));
            savedConfig = findConfig(type);
        }
        return ApiResponse.success(savedConfig);
    }

    @DeleteMapping("/approval-configs/{id}")
    @OperationAudit(
            module = "ASSET",
            type = OperationType.DELETE,
            name = "删除审批配置",
            targetType = "media_approval_config",
            targetIdParameter = "id")
    public ApiResponse<Void> deleteConfig(@PathVariable Long id) {
        assetService.deleteApprovalConfig(id);
        return ApiResponse.success();
    }

    @PostMapping("/applications")
    @Transactional
    public ApiResponse<Map<String, Object>> apply(@RequestBody Map<String, Object> body) {
        String type = configKey(required(body, "assetType"));
        Map<String, Object> config = findConfig(type);
        if (!Boolean.TRUE.equals(config.get("enabled"))) throw conflict("该流程已停用");
        Map<String, Object> data = map(body.get("formData"));
        long definitionId = number(data.get("applicationDefinitionId"));
        if (definitionId <= 0) throw validation("请从申请中心选择具体申请");
        ApplicationDefinitionView definition =
                applicationDefinitionService.requireEnabledForSubmission(
                        definitionId, number(config.get("id")));
        data.put("applicationDefinitionId", definition.id());
        data.put("applicationCode", definition.applicationCode());
        data.put("applicationName", definition.applicationName());
        List<Map<String, Object>> completeFormSchema = list(config.get("formSchema"));
        List<Map<String, Object>> formSchema =
                applicableFormSchema(completeFormSchema, definition.applicationCode());
        removeInapplicableValues(completeFormSchema, formSchema, data);
        populateControlledAutoFill(formSchema, data);
        normalizeFormData(formSchema, data);
        validateForm(formSchema, data);
        referenceService.enrichSystemOptionSnapshots(formSchema, data);
        Map<String, Object> configSettings = map(config.get("settings"));
        String completionMode =
                Objects.toString(configSettings.get("completionMode"), "handler").trim();
        if (PixelApplicationAssignmentService.COMPLETION_MODE.equals(completionMode)) {
            data.put(PixelApplicationAssignmentService.COMPLETION_MODE_KEY, completionMode);
            data.put("quantity", pixelAssignmentService.validateAndEnrichSelection(data));
        }
        CurrentUser user = SecurityContextHelper.currentUser();
        if (data.get("channelId") != null && !data.get("channelId").toString().isBlank()) {
            String channelId = data.get("channelId").toString();
            String channelName = Objects.toString(data.get("channelName"), "");
            data.put("channelId", channelId);
            data.put("channelName", channelName);
            // 旧字段暂时保留为渠道镜像，兼容存量审批记录与前端读模型。
            data.put("projectId", channelId);
            data.put("projectName", channelName);
        }
        data.put("_ccUserIds", Objects.toString(config.get("ccUserIds"), ""));
        List<Map<String, Object>> nodes = list(config.get("nodes"));
        nodes.forEach(principalService::normalizeAndResolve);
        String approvalType = Objects.toString(configSettings.get("approvalType"), "manual");
        Long sourceApplicationId =
                validateResubmissionSource(body.get("sourceApplicationId"), type, definition, user);
        String no =
                "AST"
                        + LocalDateTime.now()
                                .format(DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS"));
        long operator = user.userId();
        // 申请单必须保留提交时的组织归属，避免人员后续调部门改变审批历史口径。
        Map<String, Object> requesterDepartment =
                flowMapper.findActivePrimaryDepartment(user.userId());
        long requesterDepartmentId =
                requesterDepartment == null ? 0 : number(requesterDepartment.get("departmentId"));
        String requesterDepartmentName =
                requesterDepartmentId > 0
                        ? Objects.toString(requesterDepartment.get("departmentName"), "").trim()
                        : null;
        if (requesterDepartmentId > 0 && requesterDepartmentName != null) {
            data.put("_requesterDepartmentId", Long.toString(requesterDepartmentId));
            data.put("_requesterDepartmentName", requesterDepartmentName);
        }
        Map<String, Object> applicationRecord =
                params(
                        "applicationNo",
                        no,
                        "assetType",
                        type,
                        "title",
                        definition.applicationName(),
                        "quantity",
                        intValue(data.get("quantity"), 1),
                        "reason",
                        Objects.toString(
                                data.get("purpose"), Objects.toString(data.get("description"), "")),
                        "requesterId",
                        user.userId(),
                        "requesterName",
                        user.displayName(),
                        "departmentId",
                        requesterDepartmentId > 0 ? requesterDepartmentId : null,
                        "departmentName",
                        requesterDepartmentName,
                        "approverId",
                        number(nodes.get(0).get("approverId")),
                        "approverName",
                        required(nodes.get(0), "approverName"),
                        "formData",
                        stringify(data),
                        "formSchema",
                        stringify(formSchema),
                        "nodes",
                        stringify(nodes),
                        "sourceApplicationId",
                        sourceApplicationId,
                        "operatorId",
                        operator);
        flowMapper.insertApplication(applicationRecord);
        Long id = number(applicationRecord.get("id"));
        insertApprovalLog(
                id,
                "SUBMITTED",
                user.userId(),
                user.displayName(),
                Objects.toString(data.get("purpose"), ""),
                null,
                -1,
                "发起申请");
        if ("auto-reject".equals(approvalType)) {
            updateApplication(
                    id, "PENDING", "REJECTED", "系统按审批配置自动驳回", true, null, null, null, operator);
            insertApprovalLog(id, "REJECTED", operator, "系统自动审批", "系统按审批配置自动驳回", null, 0, "自动驳回");
            notifyUser(
                    user.userId(),
                    "申请已驳回",
                    definition.applicationName() + " 已由审批配置自动驳回",
                    "/workbench/applications?id=" + id,
                    "APPLICATION",
                    id);
        } else if ("auto-approve".equals(approvalType)) {
            Map<String, Object> handler = resolveWorkflowHandler(nodes);
            updateApplication(
                    id,
                    "PENDING",
                    "PROCESSING",
                    null,
                    false,
                    null,
                    number(handler.get("handlerId")),
                    required(handler, "handlerName"),
                    operator);
            insertApprovalLog(id, "APPROVED", operator, "系统自动审批", "系统按审批配置自动通过", null, 0, "自动通过");
            notifyUser(
                    number(handler.get("handlerId")),
                    "待处理申请",
                    body.get("title") + " 已自动通过审批，请进行业务处理",
                    "/workbench/approvals?id=" + id,
                    "PROCESSING",
                    id);
        } else {
            notifyNode(nodes.get(0), id, required(body, "title"));
        }
        return ApiResponse.success(findApplication(id));
    }

    @GetMapping("/applications/mine")
    public ApiResponse<List<Map<String, Object>>> myApplications() {
        return ApiResponse.success(
                queryApplications("requester_id=?", SecurityContextHelper.currentUserId()));
    }

    /**
     * 批量返回申请摘要，避免广告账户筛选为每条记录重复请求含审批轨迹的申请详情。
     *
     * <p>保持详情接口的参与人可见范围，单次最多查询 500 条以控制请求规模。
     */
    @GetMapping("/applications/summaries")
    public ApiResponse<List<AssetViews.ApplicationSummary>> applicationSummaries(
            @RequestParam List<Long> ids) {
        if (ids.isEmpty()) return ApiResponse.success(List.of());
        if (ids.size() > 500) throw validation("单次最多查询 500 条申请摘要");
        return ApiResponse.success(commentService.applicationSummaries(ids));
    }

    /** 返回指定广告账户的申请、金额以及审批办理轨迹，不暴露完整表单或凭据。 */
    @GetMapping("/account-lifecycle/{accountId}/applications")
    public ApiResponse<List<AssetViews.AccountLifecycleApplication>> accountLifecycleApplications(
            @PathVariable String accountId) {
        String normalizedId = accountId.trim().replaceFirst("(?i)^act_", "");
        if (!normalizedId.matches("\\d+")) throw validation("广告账户 ID 无效");
        Map<String, List<AssetViews.AccountLifecycleAction>> actionsByApplication =
                flowMapper.findAccountLifecycleActions(normalizedId).stream()
                        .map(
                                action ->
                                        Map.entry(
                                                Objects.toString(action.get("applicationId")),
                                                new AssetViews.AccountLifecycleAction(
                                                        Objects.toString(action.get("id")),
                                                        Objects.toString(action.get("action")),
                                                        Objects.toString(
                                                                action.get("actorName"), ""),
                                                        Objects.toString(
                                                                action.get("nodeName"), ""),
                                                        Objects.toString(action.get("remark"), ""),
                                                        (LocalDateTime) action.get("createdAt"))))
                        .collect(
                                java.util.stream.Collectors.groupingBy(
                                        Map.Entry::getKey,
                                        LinkedHashMap::new,
                                        java.util.stream.Collectors.mapping(
                                                Map.Entry::getValue,
                                                java.util.stream.Collectors.toList())));
        return ApiResponse.success(
                flowMapper.findAccountLifecycleApplications(normalizedId).stream()
                        .map(
                                application ->
                                        new AssetViews.AccountLifecycleApplication(
                                                Objects.toString(application.get("id")),
                                                Objects.toString(
                                                        application.get("applicationCode"), ""),
                                                Objects.toString(
                                                        application.get("title"), "广告账户操作申请"),
                                                Objects.toString(application.get("status")),
                                                Objects.toString(
                                                        application.get("requesterName"), ""),
                                                application.get("amount")
                                                                instanceof
                                                                java.math.BigDecimal amount
                                                        ? amount
                                                        : null,
                                                Objects.toString(
                                                        application.get("currency"), "USD"),
                                                (LocalDateTime) application.get("createdAt"),
                                                (LocalDateTime) application.get("decidedAt"),
                                                accountLifecycleFormFields(application),
                                                actionsByApplication.getOrDefault(
                                                        Objects.toString(application.get("id")),
                                                        List.of())))
                        .toList());
    }

    /** 从申请当时保存的表单结构和数据生成安全的只读展示字段。 */
    private List<AssetViews.AccountLifecycleFormField> accountLifecycleFormFields(
            Map<String, Object> application) {
        Map<String, Object> formData = map(parse(application.get("formData"), Map.of()));
        List<Map<String, Object>> formSchema = list(application.get("formSchema"));
        if (formData.isEmpty() || formSchema.isEmpty()) return List.of();

        String currency = Objects.toString(application.get("currency"), "USD").trim();
        List<AssetViews.AccountLifecycleFormField> result = new ArrayList<>();
        for (Map<String, Object> field : formSchema) {
            String key = Objects.toString(field.get("key"), "").trim();
            String label = Objects.toString(field.get("label"), "").trim();
            String type = Objects.toString(field.get("type"), "").trim();
            if (key.isBlank()
                    || key.startsWith("_")
                    || Set.of(
                                    "applicationCode",
                                    "applicationDefinitionId",
                                    "applicationName",
                                    "amountType",
                                    "currency")
                            .contains(key)
                    || label.isBlank()
                    || "section".equals(type)) continue;

            Object value = accountLifecycleDisplayValue(field, formData, key);
            if (isLifecycleEmptyValue(value)) continue;
            String displayValue = accountLifecycleFormatValue(value);
            if (displayValue.isBlank()) continue;
            if (Set.of("amount", "rechargeAmount").contains(key)) {
                displayValue = currency + " " + accountLifecycleFormatAmount(value);
            }
            boolean fullWidth =
                    "full".equals(field.get("width"))
                            || Set.of("textarea", "multi-select", "image-upload", "date-range")
                                    .contains(type)
                            || displayValue.length() > 80;
            result.add(
                    new AssetViews.AccountLifecycleFormField(key, label, displayValue, fullWidth));
        }
        return List.copyOf(result);
    }

    /** 系统选项优先展示提交时固化的名称，避免把内部 ID 直接暴露给用户。 */
    private Object accountLifecycleDisplayValue(
            Map<String, Object> field, Map<String, Object> formData, String key) {
        String optionSource = Objects.toString(field.get("optionSource"), "custom");
        if (!"custom".equals(optionSource)) {
            String base =
                    key.endsWith("Ids")
                            ? key.substring(0, key.length() - 3)
                            : key.endsWith("Id") ? key.substring(0, key.length() - 2) : key;
            String snapshotKey =
                    base + ("multi-select".equals(field.get("type")) ? "Names" : "Name");
            Object snapshot = formData.get(snapshotKey);
            if (!isLifecycleEmptyValue(snapshot)) return snapshot;
        }
        return formData.get(key);
    }

    private boolean isLifecycleEmptyValue(Object value) {
        if (value == null) return true;
        if (value instanceof Collection<?> collection) return collection.isEmpty();
        if (value instanceof Map<?, ?> map) return map.isEmpty();
        return value.toString().trim().isEmpty();
    }

    private String accountLifecycleFormatValue(Object value) {
        if (value instanceof Boolean bool) return bool ? "是" : "否";
        if (value instanceof Collection<?> collection) {
            return collection.stream()
                    .map(item -> accountLifecycleFormatValue(item).trim())
                    .filter(item -> !item.isBlank())
                    .collect(java.util.stream.Collectors.joining("、"));
        }
        if (value instanceof Map<?, ?>) return "";
        if (value instanceof Number number) {
            return new java.math.BigDecimal(number.toString()).stripTrailingZeros().toPlainString();
        }
        return value.toString().trim();
    }

    private String accountLifecycleFormatAmount(Object value) {
        try {
            return new java.math.BigDecimal(value.toString())
                    .setScale(2, java.math.RoundingMode.HALF_UP)
                    .toPlainString();
        } catch (NumberFormatException exception) {
            return accountLifecycleFormatValue(value);
        }
    }

    /** 返回当前流程参与人可见的最新申请详情与完整审批轨迹。 */
    @GetMapping("/applications/{id}")
    public ApiResponse<Map<String, Object>> application(@PathVariable Long id) {
        commentService.requireParticipant(id);
        return ApiResponse.success(findApplication(id));
    }

    /** 查询当前流程参与人可见的评论。 */
    @GetMapping("/applications/{id}/comments")
    public ApiResponse<List<AssetViews.ApprovalCommentView>> comments(@PathVariable Long id) {
        return ApiResponse.success(commentService.comments(id));
    }

    /** 以当前用户在流程中的真实身份发布评论。 */
    @PostMapping("/applications/{id}/comments")
    public ApiResponse<AssetViews.ApprovalCommentView> comment(
            @PathVariable Long id,
            @Valid @RequestBody AssetRequests.ApprovalCommentCreate request) {
        return ApiResponse.success(commentService.comment(id, request));
    }

    @GetMapping("/approvals")
    public ApiResponse<List<Map<String, Object>>> approvals() {
        long userId = SecurityContextHelper.currentUserId();
        List<Map<String, Object>> applications =
                flowMapper.findApplications(null, null, true).stream()
                        .map(this::decodeApplicationFields)
                        .filter(
                                item -> {
                                    if ("PROCESSING".equals(item.get("status"))) {
                                        return userId == number(item.get("handlerId"));
                                    }
                                    List<Map<String, Object>> nodes = list(item.get("nodes"));
                                    int index = intValue(item.get("currentNodeIndex"), 0);
                                    if (index >= nodes.size()) return false;
                                    Map<String, Object> node = nodes.get(index);
                                    return principalService.canApprove(node, userId);
                                })
                        .toList();
        return ApiResponse.success(enrichApplications(applications));
    }

    /** 按当前用户可见队列和服务端筛选条件分页返回审批单。 */
    @GetMapping("/approvals/page")
    public ApiResponse<AssetViews.ApprovalPage> approvalPage(
            @RequestParam(defaultValue = "pending") String queue,
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer pageSize,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Long applicationDefinitionId,
            @RequestParam(required = false) String assetType,
            @RequestParam(required = false) Long departmentId,
            @RequestParam(required = false) Long requesterId,
            @RequestParam(required = false) String decisionResult) {
        AssetApprovalQueryService.PageData result =
                approvalQueryService.page(
                        new AssetApprovalQueryService.Query(
                                queue,
                                page,
                                pageSize,
                                keyword,
                                applicationDefinitionId,
                                assetType,
                                departmentId,
                                requesterId,
                                decisionResult));
        return ApiResponse.success(
                new AssetViews.ApprovalPage(
                        result.items(),
                        result.total(),
                        result.page(),
                        result.pageSize(),
                        result.hasMore()));
    }

    /** 返回审批中心左侧队列总数及当前用户可见的筛选选项。 */
    @GetMapping("/approvals/metadata")
    public ApiResponse<AssetViews.ApprovalMetadata> approvalMetadata() {
        return ApiResponse.success(approvalQueryService.metadata());
    }

    /** 返回当前用户已通过或驳回的审批单，供审批中心的“已经审批”队列持久化展示。 */
    @GetMapping("/approvals/processed")
    public ApiResponse<List<Map<String, Object>>> processedApprovals() {
        long userId = SecurityContextHelper.currentUserId();
        return ApiResponse.success(
                decodeApplications(flowMapper.findProcessedApplications(userId)));
    }

    @PostMapping("/approvals/{id}/approve")
    public ApiResponse<Map<String, Object>> approve(
            @PathVariable Long id, @RequestBody(required = false) Map<String, Object> body) {
        Map<String, Object> request = body == null ? Map.of() : body;
        decisionService.decide(
                id,
                true,
                Objects.toString(request.get("remark"), ""),
                SecurityContextHelper.currentUser());
        return ApiResponse.success(findApplication(id));
    }

    @PostMapping("/approvals/{id}/reject")
    public ApiResponse<Map<String, Object>> reject(
            @PathVariable Long id, @RequestBody Map<String, Object> body) {
        decisionService.decide(
                id, false, required(body, "remark"), SecurityContextHelper.currentUser());
        return ApiResponse.success(findApplication(id));
    }

    /** 在新版多节点审批流中批量应用同一决定，任一失败时整批回滚。 */
    @PostMapping("/approvals/batch-decide")
    public ApiResponse<List<Map<String, Object>>> batchDecide(
            @Valid @RequestBody AssetRequests.BatchDecision request) {
        List<Long> applicationIds =
                decisionService.batchDecide(request, SecurityContextHelper.currentUser());
        return ApiResponse.success(applicationIds.stream().map(this::findApplication).toList());
    }

    /** 返回当前审批人或办理人主部门内可接收转交的其他同事。 */
    @GetMapping("/approvals/{id}/transfer-candidates")
    public ApiResponse<List<AssetViews.ApprovalTransferCandidate>> transferCandidates(
            @PathVariable Long id) {
        return ApiResponse.success(
                transferService.candidates(id, SecurityContextHelper.currentUser()));
    }

    /** 将当前审批或办理节点转交给负责人主部门内的其他同事。 */
    @PostMapping("/approvals/{id}/transfer")
    public ApiResponse<Map<String, Object>> transfer(
            @PathVariable Long id, @Valid @RequestBody AssetRequests.ApprovalTransfer request) {
        transferService.transfer(id, request, SecurityContextHelper.currentUser());
        return ApiResponse.success(findApplication(id));
    }

    @PostMapping("/approvals/{id}/complete")
    @Transactional
    public ApiResponse<Map<String, Object>> complete(
            @PathVariable Long id, @RequestBody Map<String, Object> body) {
        return completeProcessing(
                id,
                required(body, "remark"),
                longList(body.get("assetIds")),
                map(body.get("actionData")));
    }

    /** 返回当前用户是否存在未读通知，用于顶部导航红点。 */
    @GetMapping("/notifications/unread-status")
    public ApiResponse<AssetViews.NotificationUnreadStatus> notificationUnreadStatus() {
        return ApiResponse.success(notificationService.unreadStatus());
    }

    /** 分页返回当前用户的站内通知。 */
    @GetMapping("/notifications")
    public ApiResponse<AssetViews.NotificationPage> notifications(
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(notificationService.notifications(page, pageSize));
    }

    @PutMapping("/notifications/{id}/read")
    public ApiResponse<Void> read(@PathVariable Long id) {
        notificationService.markRead(id);
        return ApiResponse.success();
    }

    @PutMapping("/notifications/read-all")
    public ApiResponse<Void> readAll() {
        notificationService.markAllRead();
        return ApiResponse.success();
    }

    private ApiResponse<Map<String, Object>> completeProcessing(
            Long id, String remark, List<Long> selectedAssetIds, Map<String, Object> actionData) {
        if (flowMapper.lockApplication(id) == null) throw notFound("申请单");
        Map<String, Object> application = findApplication(id);
        if (!"PROCESSING".equals(application.get("status"))) throw conflict("申请不在待处理阶段");
        long userId = SecurityContextHelper.currentUserId();
        if (userId != number(application.get("handlerId"))) throw conflict("您不是该流程的处理人");
        validateHandlerActionData(application, actionData, userId);
        String applicationType = Objects.toString(application.get("assetType"), "");
        boolean accountOpening = "ACCOUNT_OPENING".equals(applicationType);
        List<Map<String, Object>> allocatedAssetSnapshots =
                requiresAssetAllocation(applicationType)
                        ? allocateAssets(application, selectedAssetIds, userId)
                        : List.of();
        if (accountOpening) {
            String openedAccountIds = Objects.toString(actionData.get("openedAccountIds"), "");
            List<AccountOpeningChannelAccountService.SelectedAccount> assignedAccounts =
                    channelAccountService.assignSelectedAccounts(
                            openedAccountIds,
                            number(application.get("id")),
                            number(application.get("requesterId")),
                            Objects.toString(application.get("requesterName"), ""),
                            userId);
            allocatedAssetSnapshots =
                    assignedAccounts.stream()
                            .map(
                                    account ->
                                            Map.<String, Object>of(
                                                    "id", account.accountId(),
                                                    "assetType", "AD_ACCOUNT",
                                                    "assetName", account.accountId(),
                                                    "assetCode", account.accountId(),
                                                    "channelName", account.channelName()))
                            .toList();
        }
        Map<String, Object> persistedActionData = new LinkedHashMap<>(actionData);
        if ("PROJECT_CLOSURE".equals(applicationType)) {
            Map<String, Object> formData = map(application.get("formData"));
            String projectId = Objects.toString(formData.get("projectId"), "").trim();
            if (projectId.isBlank()) throw validation("结项申请缺少项目");
            persistedActionData.put(
                    "releasedPixelCount", assetService.releasePixelsForProject(projectId, userId));
        }
        if (!allocatedAssetSnapshots.isEmpty()) {
            // 办理记录保留非敏感分配快照，资产后续回收解绑后仍可审计原办理结果。
            persistedActionData.put("_allocatedAssets", allocatedAssetSnapshots);
        }
        CurrentUser actor = SecurityContextHelper.currentUser();
        insertApprovalLog(
                id,
                "COMPLETED",
                actor.userId(),
                actor.displayName(),
                remark,
                stringify(persistedActionData),
                list(application.get("nodes")).size(),
                "业务办理");
        updateApplication(id, "PROCESSING", "APPROVED", remark, true, null, null, null, userId);
        notifyCompletion(application, id);
        return ApiResponse.success(findApplication(id));
    }

    private List<Map<String, Object>> allocateAssets(
            Map<String, Object> application, List<Long> selectedAssetIds, long operatorId) {
        String applicationType = Objects.toString(application.get("assetType"), "");
        Map<String, Object> handlerAction = map(application.get("handlerAction"));
        Map<String, Object> assignment = map(handlerAction.get("resourceAssignment"));
        // 兼容配置改造前已发起的存量申请；新申请完全由办理节点快照控制。
        boolean legacyInventoryFlow =
                handlerAction.isEmpty() && INVENTORY_TYPES.contains(applicationType);
        if (!Boolean.TRUE.equals(assignment.get("enabled")) && !legacyInventoryFlow) {
            if (!selectedAssetIds.isEmpty()) throw validation("当前办理节点未配置资源分配");
            return List.of();
        }
        Map<String, Object> applicationData = map(application.get("formData"));
        AssetService.InventorySelection inventorySelection =
                assetService.resolveInventorySelection(
                        applicationType, applicationData, assignment);
        String quantityFieldKey =
                Objects.toString(assignment.get("quantityFieldKey"), "quantity").trim();
        int quantity = intValue(applicationData.get(quantityFieldKey), 1);
        if (selectedAssetIds.size() != quantity) {
            throw validation("请选择" + quantity + "个资产后再完成处理");
        }
        long assigneeId = number(applicationData.get("resourceAssigneeId"));
        String assigneeName =
                Objects.toString(applicationData.get("resourceAssigneeName"), "").trim();
        if (assigneeId <= 0 || assigneeName.isBlank()) {
            assigneeId = number(application.get("requesterId"));
            assigneeName = Objects.toString(application.get("requesterName"), "");
        }
        List<Map<String, Object>> selectedAssets = flowMapper.lockAssets(selectedAssetIds);
        if (selectedAssets.size() != selectedAssetIds.size()) {
            throw conflict("所选资产不存在或已删除，请刷新后重新选择");
        }
        if (selectedAssets.stream()
                .anyMatch(
                        asset ->
                                !inventorySelection
                                        .assetType()
                                        .equals(Objects.toString(asset.get("assetType"), "")))) {
            throw conflict("所选资产类型与申请类型不一致");
        }
        boolean hasUnavailableAsset =
                selectedAssets.stream()
                        .anyMatch(
                                asset ->
                                        !"AVAILABLE"
                                                .equals(Objects.toString(asset.get("status"), "")));
        if (hasUnavailableAsset) {
            String message =
                    "PIXEL".equals(inventorySelection.assetType())
                            ? "所选像素已分配给项目，请刷新后重新选择"
                            : "所选资产已被分配或不可用，请刷新后重新选择";
            throw conflict(message);
        }
        if (!inventorySelection.subtype().isBlank()
                && selectedAssets.stream()
                        .anyMatch(
                                asset ->
                                        !assetService.matchesInventorySubtype(
                                                Objects.toString(asset.get("secretData"), null),
                                                inventorySelection.subtype()))) {
            throw conflict("所选资产与申请的社交资产类型不一致");
        }
        String channelFieldKey =
                Objects.toString(assignment.get("channelFieldKey"), "channelId").trim();
        String expectedChannelId =
                channelFieldKey.isBlank()
                        ? ""
                        : Objects.toString(applicationData.get(channelFieldKey), "").trim();
        if (!"PIXEL".equals(inventorySelection.assetType())
                && !expectedChannelId.isBlank()
                && selectedAssets.stream()
                        .anyMatch(
                                asset ->
                                        !expectedChannelId.equals(
                                                Objects.toString(asset.get("channelId"), "")))) {
            throw conflict("所选资产不属于申请渠道，请刷新后重新选择");
        }
        String resolvedPixelProjectId = "";
        String resolvedPixelProjectName = "";
        String resolvedPixelUsageTeam = "";
        if ("PIXEL".equals(inventorySelection.assetType())) {
            resolvedPixelProjectId = Objects.toString(applicationData.get("projectId"), "").trim();
            resolvedPixelProjectName =
                    Objects.toString(applicationData.get("projectName"), "").trim();
            if (resolvedPixelProjectId.isBlank() || resolvedPixelProjectName.isBlank()) {
                throw validation("像素申请缺少项目");
            }
            String usageTeamId = Objects.toString(applicationData.get("usageTeamId"), "").trim();
            resolvedPixelUsageTeam =
                    Objects.toString(applicationData.get("usageTeamName"), "").trim();
            if (usageTeamId.isBlank() || resolvedPixelUsageTeam.isBlank()) {
                throw validation("像素申请缺少使用团队");
            }
        }
        final String pixelProjectId = resolvedPixelProjectId;
        final String pixelProjectName = resolvedPixelProjectName;
        final String pixelUsageTeam = resolvedPixelUsageTeam;
        for (Map<String, Object> asset : selectedAssets) {
            Long assetId = number(asset.get("id"));
            int updated =
                    "PIXEL".equals(inventorySelection.assetType())
                            ? flowMapper.assignPixelAsset(
                                    params(
                                            "applicationId", application.get("id"),
                                            "projectId", pixelProjectId,
                                            "projectName", pixelProjectName,
                                            "usageTeam", pixelUsageTeam,
                                            "operatorId", operatorId,
                                            "assetId", assetId))
                            : flowMapper.assignAsset(
                                    params(
                                            "applicationId",
                                            application.get("id"),
                                            "assigneeId",
                                            assigneeId,
                                            "assigneeName",
                                            assigneeName,
                                            "operatorId",
                                            operatorId,
                                            "assetId",
                                            assetId));
            if (updated != 1) throw conflict("所选资产状态已变化，请刷新后重新选择");
            assetService.recordLifecycleAllocation(assetId);
        }
        return selectedAssets.stream()
                .map(
                        asset -> {
                            Map<String, Object> snapshot = new LinkedHashMap<>();
                            snapshot.put("id", number(asset.get("id")));
                            snapshot.put("assetType", asset.get("assetType"));
                            snapshot.put("assetName", asset.get("assetName"));
                            snapshot.put("assetCode", asset.get("assetCode"));
                            snapshot.put("channelName", asset.get("channelName"));
                            snapshot.put("projectName", asset.get("projectName"));
                            return snapshot;
                        })
                .toList();
    }

    private void notifyCompletion(Map<String, Object> application, Long id) {
        notifyUser(
                number(application.get("requesterId")),
                "申请已完成",
                application.get("title") + " 已完成处理与分配",
                "/workbench/applications?id=" + id,
                "APPLICATION",
                id);
        for (String cc :
                Objects.toString(map(application.get("formData")).get("_ccUserIds"), "")
                        .split(",")) {
            long ccId = number(cc.trim());
            if (ccId > 0)
                notifyUser(
                        ccId,
                        "审批抄送",
                        application.get("title") + " 已完成处理与分配",
                        "/workbench/applications?id=" + id,
                        "CC",
                        id);
        }
    }

    private Map<String, Object> findConfig(String type) {
        Map<String, Object> row = flowMapper.findConfig(type);
        if (row == null) throw conflict("该审批配置不存在或已删除");
        return decodeConfig(row);
    }

    private Map<String, Object> findApplication(Long id) {
        List<Map<String, Object>> rows = queryApplications("id=?", id);
        if (rows.isEmpty()) throw notFound("申请单");
        return rows.get(0);
    }

    /**
     * 校验重提来源，确保新申请只能追溯到当前申请人名下同一申请入口的已驳回单。
     *
     * @param sourceValue 请求中的上一张申请 ID；缺失时表示普通新申请
     * @return 已校验的来源 ID；普通新申请返回 {@code null}
     */
    private Long validateResubmissionSource(
            Object sourceValue,
            String assetType,
            ApplicationDefinitionView definition,
            CurrentUser user) {
        long sourceId = number(sourceValue);
        if (sourceId <= 0) return null;

        Map<String, Object> source = findApplication(sourceId);
        if (!Objects.equals(number(source.get("requesterId")), user.userId())) {
            throw conflict("只能重新提交本人发起的申请");
        }
        if (!"REJECTED".equals(source.get("status"))) {
            throw conflict("只有已驳回的申请可以重新提交");
        }
        if (!assetType.equals(source.get("assetType"))) {
            throw validation("重提申请必须使用原申请的审批类型");
        }
        Map<String, Object> sourceFormData = map(source.get("formData"));
        if (number(sourceFormData.get("applicationDefinitionId")) != number(definition.id())) {
            throw validation("重提申请必须使用原申请入口");
        }
        return sourceId;
    }

    private List<Map<String, Object>> queryApplications(String where, Object... args) {
        Long id = "id=?".equals(where) ? number(args[0]) : null;
        Long requesterId = "requester_id=?".equals(where) ? number(args[0]) : null;
        boolean activeOnly = "status IN ('PENDING','PROCESSING')".equals(where);
        return decodeApplications(flowMapper.findApplications(id, requesterId, activeOnly));
    }

    /** 查询审批配置；管理视图保留停用项，申请视图只返回当前用户可发起的已启用项。 */
    private List<Map<String, Object>> queryConfigs(boolean managementView) {
        long userId = SecurityContextHelper.currentUserId();
        return flowMapper.findConfigs(userId, managementView).stream()
                .map(this::decodeConfig)
                .toList();
    }

    /** 像素选择接口只投影业务检索字段，禁止把解密后的凭据返回申请页面。 */
    private Map<String, Object> selectablePixelView(MediaAsset asset) {
        Map<String, Object> details = map(parse(asset.getSecretData(), Map.of()));
        return params(
                "id", Objects.toString(asset.getId()),
                "pixelId", firstText(details.get("pixelId"), asset.getAssetCode()),
                "pixelName", firstText(details.get("pixelName"), asset.getAssetName()),
                "bmId", Objects.toString(details.get("bmId"), ""),
                "bmName", Objects.toString(details.get("bmName"), ""),
                "pixelTestCode", Objects.toString(details.get("pixelTestCode"), ""),
                "createdAt", asset.getCreatedAt(),
                "remark", Objects.toString(asset.getRemark(), ""));
    }

    private String firstText(Object primary, Object fallback) {
        String value = Objects.toString(primary, "").trim();
        return value.isBlank() ? Objects.toString(fallback, "").trim() : value;
    }

    private Map<String, Object> decodeConfig(Map<String, Object> row) {
        row.put("formSchema", parse(row.get("formSchema"), List.of()));
        row.put("nodes", parse(row.get("nodes"), List.of()));
        row.put("settings", parse(row.get("settings"), Map.of()));
        boolean pixelAutoAssignment =
                PixelApplicationAssignmentService.COMPLETION_MODE.equals(
                        Objects.toString(map(row.get("settings")).get("completionMode"), ""));
        Map<String, Object> handler =
                pixelAutoAssignment ? Map.of() : resolveWorkflowHandler(list(row.get("nodes")));
        row.put("handlerId", number(handler.get("handlerId")));
        row.put("handlerName", Objects.toString(handler.get("handlerName"), ""));
        row.put("handlerSource", Objects.toString(handler.get("handlerSource"), "fixed-user"));
        row.put(
                "handlerApprovalNodeId",
                Objects.toString(handler.get("handlerApprovalNodeId"), ""));
        row.put("enabled", intValue(row.get("enabled"), 0) == 1);
        String storedCategory = Objects.toString(row.get("category"), "");
        row.put("category", CATEGORIES.contains(storedCategory) ? storedCategory : "advertising");
        row.put("usageCount", number(row.get("usageCount")));
        row.put("sortOrder", intValue(row.get("sortOrder"), 0));
        String definitionIds = Objects.toString(row.get("applicationDefinitionIds"), "");
        row.put(
                "applicationDefinitionIds",
                definitionIds.isBlank() ? List.of() : Arrays.asList(definitionIds.split(",")));
        row.put("status", "published");
        return row;
    }

    /** 批量解码申请列表并补齐关联数据，将原先每张申请两次关联查询压缩为每批两次查询。 */
    private List<Map<String, Object>> decodeApplications(List<Map<String, Object>> rows) {
        return enrichApplications(rows.stream().map(this::decodeApplicationFields).toList());
    }

    /** 解码申请自身字段；审批列表会先完成权限过滤，再批量加载关联数据。 */
    private Map<String, Object> decodeApplicationFields(Map<String, Object> row) {
        Object sourceApplicationId = row.get("sourceApplicationId");
        if (sourceApplicationId != null) {
            // 与申请单 ID 保持同一传输口径，避免前端在大整数场景丢失来源关联。
            row.put("sourceApplicationId", sourceApplicationId.toString());
        }
        Map<String, Object> formData = map(parse(row.get("formData"), Map.of()));
        row.put("formData", formData);
        applyRequesterDepartmentSnapshot(row, formData);
        row.put("formSchema", parse(row.get("formSchema"), List.of()));
        row.put("nodes", parse(row.get("nodes"), List.of()));
        Map<String, Object> handler =
                PixelApplicationAssignmentService.COMPLETION_MODE.equals(
                                Objects.toString(
                                        formData.get(
                                                PixelApplicationAssignmentService
                                                        .COMPLETION_MODE_KEY),
                                        ""))
                        ? Map.of()
                        : resolveWorkflowHandler(list(row.get("nodes")));
        row.put("handlerId", number(handler.get("handlerId")));
        row.put("handlerName", Objects.toString(handler.get("handlerName"), ""));
        row.put("handlerSource", Objects.toString(handler.get("handlerSource"), "fixed-user"));
        row.put(
                "handlerApprovalNodeId",
                Objects.toString(handler.get("handlerApprovalNodeId"), ""));
        row.put("handlerAction", map(handler.get("handlerAction")));
        return row;
    }

    /** 从申请提交时固化的表单快照回填部门，兼容尚未执行部门列迁移的环境。 */
    private void applyRequesterDepartmentSnapshot(
            Map<String, Object> application, Map<String, Object> formData) {
        String departmentId = Objects.toString(application.get("departmentId"), "").trim();
        String departmentName = Objects.toString(application.get("departmentName"), "").trim();
        if (departmentId.isBlank()) {
            departmentId = Objects.toString(formData.get("_requesterDepartmentId"), "").trim();
        }
        if (departmentName.isBlank()) {
            departmentName = Objects.toString(formData.get("_requesterDepartmentName"), "").trim();
        }
        if (!departmentId.isBlank()) application.put("departmentId", departmentId);
        if (!departmentName.isBlank()) application.put("departmentName", departmentName);
    }

    /** 按申请 ID 批量回填审批轨迹和资产摘要，空列表不访问数据库。 */
    private List<Map<String, Object>> enrichApplications(List<Map<String, Object>> applications) {
        if (applications.isEmpty()) return applications;

        ccUserService.enrichApplications(applications);

        List<Long> applicationIds =
                applications.stream().map(item -> number(item.get("id"))).distinct().toList();
        Map<Long, List<Map<String, Object>>> logsByApplicationId =
                flowMapper.findApprovalLogsByApplicationIds(applicationIds).stream()
                        .peek(log -> log.put("actionData", parse(log.get("actionData"), Map.of())))
                        .collect(
                                java.util.stream.Collectors.groupingBy(
                                        log -> number(log.get("applicationId")),
                                        LinkedHashMap::new,
                                        java.util.stream.Collectors.toList()));
        Map<Long, List<Map<String, Object>>> assetsByApplicationId =
                flowMapper.findAllocatedAssetsByApplicationIds(applicationIds).stream()
                        .collect(
                                java.util.stream.Collectors.groupingBy(
                                        asset -> number(asset.get("applicationId")),
                                        LinkedHashMap::new,
                                        java.util.stream.Collectors.toList()));

        logsByApplicationId
                .values()
                .forEach(logs -> logs.forEach(log -> log.remove("applicationId")));
        assetsByApplicationId
                .values()
                .forEach(assets -> assets.forEach(asset -> asset.remove("applicationId")));

        applications.forEach(
                application -> {
                    long applicationId = number(application.get("id"));
                    application.put(
                            "approvalLogs",
                            logsByApplicationId.getOrDefault(applicationId, List.of()).stream()
                                    .filter(log -> !"TRANSFERRED".equals(log.get("action")))
                                    .toList());
                    application.put(
                            "transferRecords",
                            transferRecords(
                                    logsByApplicationId.getOrDefault(applicationId, List.of())));
                    application.put(
                            "allocatedAssets",
                            assetsByApplicationId.getOrDefault(applicationId, List.of()));
                });
        return applications;
    }

    /** 将转交日志转换为前端稳定审计模型，避免把转交误判成审批通过。 */
    private List<Map<String, Object>> transferRecords(List<Map<String, Object>> logs) {
        return logs.stream()
                .filter(log -> "TRANSFERRED".equals(log.get("action")))
                .map(
                        log -> {
                            Map<String, Object> actionData = map(log.get("actionData"));
                            Map<String, Object> record = new LinkedHashMap<>();
                            record.put("id", Objects.toString(log.get("id"), ""));
                            record.put("actorId", Objects.toString(log.get("actorId"), ""));
                            record.put("actorName", Objects.toString(log.get("actorName"), ""));
                            record.put("nodeIndex", intValue(log.get("nodeIndex"), 0));
                            record.put("actorDepartmentId", actionData.get("actorDepartmentId"));
                            record.put(
                                    "actorDepartmentName", actionData.get("actorDepartmentName"));
                            record.put("recipientId", actionData.get("recipientId"));
                            record.put("recipientName", actionData.get("recipientName"));
                            record.put(
                                    "recipientDepartmentId",
                                    actionData.get("recipientDepartmentId"));
                            record.put(
                                    "recipientDepartmentName",
                                    actionData.get("recipientDepartmentName"));
                            record.put("remark", Objects.toString(log.get("remark"), ""));
                            record.put("at", log.get("createdAt"));
                            return record;
                        })
                .toList();
    }

    /** 解析申请快照中的办理人；办理节点可复用指定审批节点的审批人。 */
    private Map<String, Object> resolveWorkflowHandler(List<Map<String, Object>> nodes) {
        if (nodes.isEmpty()) return Map.of("handlerId", 0L, "handlerName", "");
        Map<String, Object> last = nodes.get(nodes.size() - 1);
        Map<String, Object> handlerNode = last;
        boolean followsApprovalNode =
                "approval-node".equals(Objects.toString(last.get("handlerSource"), ""));
        if (followsApprovalNode) {
            String approvalNodeId = Objects.toString(last.get("handlerApprovalNodeId"), "").trim();
            for (Map<String, Object> node : nodes) {
                if (approvalNodeId.equals(Objects.toString(node.get("id"), ""))) {
                    handlerNode = node;
                    break;
                }
            }
        }
        long handlerId = number(last.get("handlerId"));
        String handlerName = Objects.toString(last.get("handlerName"), "");
        if (followsApprovalNode && handlerId <= 0) {
            handlerId = number(handlerNode.get("approverId"));
            handlerName = Objects.toString(handlerNode.get("approverName"), "");
        }
        if (handlerId <= 0) {
            handlerId = number(last.get("approverId"));
            handlerName = Objects.toString(last.get("approverName"), "");
        }
        Map<String, Object> handler = new LinkedHashMap<>();
        handler.put("handlerId", handlerId);
        handler.put("handlerName", handlerName);
        handler.put("handlerSource", Objects.toString(last.get("handlerSource"), "fixed-user"));
        handler.put(
                "handlerApprovalNodeId", Objects.toString(last.get("handlerApprovalNodeId"), ""));
        handler.put("handlerAction", map(last.get("handlerAction")));
        return handler;
    }

    private void notifyNode(Map<String, Object> node, Long id, String title) {
        principalService
                .normalizeAndResolve(node)
                .eligibleUserIds()
                .forEach(
                        userId ->
                                notifyUser(
                                        userId,
                                        "待审批申请",
                                        title + " 已到达「" + node.get("name") + "」",
                                        "/workbench/approvals?id=" + id,
                                        "APPROVAL",
                                        id));
    }

    private void notifyUser(
            long userId, String title, String content, String path, String type, Long businessId) {
        if (userId <= 0) return;
        deliveryNotificationService.notify(
                new NotificationMessage(title, content, path, type, businessId),
                NotificationRecipients.users(List.of(userId)));
    }

    /** 申请表中的接口回填只允许受控数据源，并在服务端重新计算，避免篡改只读值。 */
    private void populateControlledAutoFill(
            List<Map<String, Object>> fields, Map<String, Object> data) {
        Map<Long, Map<String, Object>> paymentContexts = new HashMap<>();
        for (Map<String, Object> field : fields) {
            Map<String, Object> autoFill = map(field.get("autoFill"));
            if (autoFill.isEmpty()) continue;
            if (!"channel-payment-context".equals(autoFill.get("source"))) {
                throw validation("不支持的接口联动数据源");
            }
            long channelId = number(data.get(required(autoFill, "triggerFieldKey")));
            if (channelId <= 0) continue;
            Map<String, Object> context =
                    paymentContexts.computeIfAbsent(channelId, this::loadChannelPaymentContext);
            String resultKey = required(autoFill, "resultKey");
            if (!Set.of("channelYesterdayCost", "paymentAddress").contains(resultKey)) {
                throw validation("不支持的接口回填结果");
            }
            data.put(required(field, "key"), context.get(resultKey));
        }
    }

    private Map<String, Object> loadChannelPaymentContext(long channelId) {
        Map<String, Object> channel = flowMapper.findChannelPaymentContext(channelId);
        if (channel == null) throw validation("所选渠道不存在或已停用");
        Map<String, Object> context = new LinkedHashMap<>(channel);
        Object spend = flowMapper.sumYesterdayChannelSpend(channelId);
        context.put("channelYesterdayCost", spend);
        return context;
    }

    private void validateHandlerAction(String applicationType, Map<String, Object> handlerAction) {
        if (handlerAction.isEmpty()) return;
        Map<String, Object> assignment = map(handlerAction.get("resourceAssignment"));
        if (Boolean.TRUE.equals(assignment.get("enabled"))) {
            if (!"application".equals(assignment.get("assetTypeSource"))) {
                throw validation("资源分配类型必须跟随申请类型");
            }
            validateFieldKey(
                    Objects.toString(assignment.get("quantityFieldKey"), "quantity"), "数量字段");
            String assetTypeKey = Objects.toString(assignment.get("assetTypeFieldKey"), "");
            if (!assetTypeKey.isBlank()) validateFieldKey(assetTypeKey, "实际资产类型字段");
            String channelKey = Objects.toString(assignment.get("channelFieldKey"), "");
            if (!channelKey.isBlank()) validateFieldKey(channelKey, "渠道字段");
        }
        List<Map<String, Object>> fields = list(handlerAction.get("formSchema"));
        Set<String> keys = new HashSet<>();
        for (Map<String, Object> field : fields) {
            String key = required(field, "key");
            validateFieldKey(key, "办理字段");
            if (!keys.add(key)) throw validation("办理表单字段标识不能重复：" + key);
            required(field, "label");
            String type = required(field, "type");
            if (!Set.of("image-upload", "number", "text", "textarea").contains(type)) {
                throw validation("不支持的办理控件类型：" + type);
            }
            long maxLength = number(field.get("maxLength"));
            if (maxLength < 0 || maxLength > 10000) {
                throw validation(field.get("label") + "的最大长度必须在 1 到 10000 之间");
            }
            if (field.get("minValue") != null
                    && field.get("maxValue") != null
                    && decimal(field.get("minValue")) > decimal(field.get("maxValue"))) {
                throw validation(field.get("label") + "的最小值不能大于最大值");
            }
            if ("image-upload".equals(type)) {
                int maxCount = intValue(field.get("maxCount"), 1);
                int maxFileSizeMb = intValue(field.get("maxFileSizeMb"), 3);
                if (maxCount < 1 || maxCount > 9) throw validation("图片数量必须在 1 到 9 之间");
                if (maxFileSizeMb < 1 || maxFileSizeMb > 20) {
                    throw validation("单张图片大小必须在 1MB 到 20MB 之间");
                }
                if (!Objects.toString(field.get("accept"), "image/*").startsWith("image/")) {
                    throw validation("图片上传控件只允许配置图片类型");
                }
            }
        }
    }

    /** 开户申请通过开户专用流程选择账户；包括像素在内的其他库存申请均走统一资产分配。 */
    static boolean requiresAssetAllocation(String applicationType) {
        return !"ACCOUNT_OPENING".equals(applicationType);
    }

    private void validateFieldKey(String key, String label) {
        if (!key.matches("^[A-Za-z][A-Za-z0-9_]{0,39}$")) {
            throw validation(label + "标识仅支持字母、数字和下划线，且必须以字母开头");
        }
    }

    private void validateHandlerActionData(
            Map<String, Object> application, Map<String, Object> actionData, long userId) {
        Map<String, Object> handlerAction = map(application.get("handlerAction"));
        List<Map<String, Object>> fields = list(handlerAction.get("formSchema"));
        Set<String> allowedKeys =
                fields.stream()
                        .map(field -> Objects.toString(field.get("key"), ""))
                        .collect(java.util.stream.Collectors.toSet());
        actionData.keySet().removeIf(key -> !allowedKeys.contains(key));
        validateForm(fields, actionData);
        for (Map<String, Object> field : fields) {
            if (!"image-upload".equals(field.get("type"))) continue;
            List<Long> fileIds = fileIdList(actionData.get(required(field, "key")));
            int maxCount = intValue(field.get("maxCount"), 1);
            if (fileIds.size() > maxCount) {
                throw validation(field.get("label") + "最多上传" + maxCount + "张图片");
            }
            if (fileIds.isEmpty()) continue;
            Map<String, Object> fileSummary = flowMapper.summarizeOwnedFiles(fileIds, userId);
            if (number(fileSummary.get("fileCount")) != fileIds.size()) {
                throw validation(field.get("label") + "包含无效图片，请重新上传");
            }
            long maxBytes = intValue(field.get("maxFileSizeMb"), 3) * 1024L * 1024L;
            if (number(fileSummary.get("maxFileSize")) > maxBytes) {
                throw validation(
                        field.get("label")
                                + "单张不能超过"
                                + intValue(field.get("maxFileSizeMb"), 3)
                                + "MB");
            }
        }
    }

    private List<Long> fileIdList(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object item : values) {
            long id = number(item);
            if (id <= 0 || !ids.add(id)) throw validation("上传文件标识不合法");
        }
        return new ArrayList<>(ids);
    }

    private void validateTemplate(
            List<Map<String, Object>> fields, List<Map<String, Object>> nodes) {
        if (fields.isEmpty()) throw validation("动态表单至少需要一个字段");
        if (nodes.isEmpty()) throw validation("审批流至少需要一个审批节点");
        Set<String> keys = new HashSet<>();
        int inputFieldCount = 0;
        for (Map<String, Object> field : fields) {
            String key = required(field, "key");
            if (!key.matches("^[A-Za-z][A-Za-z0-9_]{0,39}$")) {
                throw validation("表单字段标识仅支持字母、数字和下划线，且必须以字母开头");
            }
            required(field, "label");
            String type = required(field, "type");
            if (!Set.of(
                            "date",
                            "date-range",
                            "multi-select",
                            "number",
                            "pixel-selector",
                            "section",
                            "select",
                            "text",
                            "textarea")
                    .contains(type)) throw validation("不支持的表单控件类型：" + type);
            if (!keys.add(key)) throw validation("表单字段标识不能重复：" + key);
            if ("section".equals(type)) continue;
            inputFieldCount++;
            String source = Objects.toString(field.get("optionSource"), "custom");
            if ("pixel-selector".equals(type) && !"available-pixels".equals(source)) {
                throw validation("像素选择控件必须使用可用像素数据源");
            }
            if (("select".equals(type) || "multi-select".equals(type))
                    && !Set.of(
                                    "custom",
                                    "departments",
                                    "users",
                                    "projects",
                                    "roles",
                                    "channels",
                                    "ad-accounts")
                            .contains(source)) {
                throw validation("不支持的下拉选项来源：" + source);
            }
            if (("select".equals(type) || "multi-select".equals(type))
                    && "custom".equals(source)
                    && stringList(field.get("options")).isEmpty()) {
                throw validation(field.get("label") + "至少需要一个自定义选项");
            }
            long maxLength = number(field.get("maxLength"));
            if (maxLength < 0 || maxLength > 10000) {
                throw validation(field.get("label") + "的最大长度必须在 1 到 10000 之间");
            }
        }
        if (inputFieldCount == 0) throw validation("动态表单至少需要一个可填写字段");
        for (Map<String, Object> field : fields) {
            if ("section".equals(field.get("type"))) continue;
            validateFieldCondition(field.get("visibleWhen"), keys, field.get("label"));
            validateFieldCondition(field.get("requiredWhen"), keys, field.get("label"));
            Map<String, Object> autoFill = map(field.get("autoFill"));
            if (!autoFill.isEmpty()) {
                if (!"channel-payment-context".equals(autoFill.get("source"))) {
                    throw validation("不支持的接口联动数据源");
                }
                String triggerFieldKey = required(autoFill, "triggerFieldKey");
                if (!keys.contains(triggerFieldKey)) throw validation("接口联动触发字段不存在");
                if (!Set.of("channelYesterdayCost", "paymentAddress")
                        .contains(required(autoFill, "resultKey"))) {
                    throw validation("不支持的接口回填结果");
                }
            }
        }
        for (Map<String, Object> node : nodes) {
            required(node, "name");
            principalService.normalizeAndResolve(node);
        }
    }

    private void validateFieldCondition(Object value, Set<String> keys, Object label) {
        if (!(value instanceof Map<?, ?>)) return;
        Map<String, Object> condition = map(value);
        String fieldKey = required(condition, "fieldKey");
        if (!keys.contains(fieldKey)) throw validation(label + "引用的条件字段不存在");
        String operator = required(condition, "operator");
        if (!Set.of("equals", "not-equals", "in").contains(operator)) {
            throw validation(label + "的条件运算符不受支持");
        }
    }

    private boolean activeUser(long id) {
        return flowMapper.countActiveUser(id) == 1;
    }

    private void validateForm(List<Map<String, Object>> fields, Map<String, Object> data) {
        for (Map<String, Object> field : fields) {
            if ("section".equals(field.get("type"))) continue;
            if (field.get("visibleWhen") != null
                    && !conditionMatches(field.get("visibleWhen"), data)) continue;
            Object value = data.get(Objects.toString(field.get("key"), ""));
            boolean required =
                    Boolean.TRUE.equals(field.get("required"))
                            || conditionMatches(field.get("requiredWhen"), data);
            if (required && isEmptyValue(value)) {
                throw validation("请填写" + field.get("label"));
            }
            if (isEmptyValue(value)) continue;
            long maxLengthValue = number(field.get("maxLength"));
            int maxLength = maxLengthValue > 0 ? Math.toIntExact(maxLengthValue) : 0;
            if (maxLength > 0 && value.toString().length() > maxLength) {
                throw validation(field.get("label") + "不能超过" + maxLength + "个字符");
            }
            String rule = Objects.toString(field.get("validationRule"), "");
            String normalized = value.toString().replace('：', ':').replace('；', ';');
            if ("digit-list".equals(rule) && !validDigitList(normalized)) {
                throw validation(field.get("label") + "仅支持数字，多个值请用分号分隔");
            }
            if ("pixel-list".equals(rule) && !validPixelList(normalized)) {
                throw validation(field.get("label") + "格式错误，请按“像素名称:像素ID”填写");
            }
            if ("email".equals(rule) && !normalized.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
                throw validation(field.get("label") + "格式不正确");
            }
            if ("url".equals(rule) && !normalized.matches("^https?://.+")) {
                throw validation(field.get("label") + "仅支持 http 或 https 链接");
            }
            if ("positive-money".equals(rule) && decimal(value) <= 0) {
                throw validation(field.get("label") + "必须大于0");
            }
            if ("number".equals(field.get("type"))) {
                double numberValue = decimal(value);
                if (field.get("minValue") != null && numberValue < decimal(field.get("minValue"))) {
                    throw validation(field.get("label") + "不能小于" + field.get("minValue"));
                }
                if (field.get("maxValue") != null && numberValue > decimal(field.get("maxValue"))) {
                    throw validation(field.get("label") + "不能大于" + field.get("maxValue"));
                }
            }
            String source = Objects.toString(field.get("optionSource"), "custom");
            if (("select".equals(field.get("type")) || "multi-select".equals(field.get("type")))
                    && "custom".equals(source)) {
                Set<String> allowed = new LinkedHashSet<>(stringList(field.get("options")));
                List<String> selected =
                        value instanceof List<?> ? stringList(value) : List.of(value.toString());
                if (!allowed.containsAll(selected)) {
                    throw validation(field.get("label") + "包含无效选项，请重新选择");
                }
            }
        }
    }

    private boolean conditionMatches(Object value, Map<String, Object> data) {
        if (!(value instanceof Map<?, ?>)) return false;
        Map<String, Object> condition = map(value);
        String current = Objects.toString(data.get(condition.get("fieldKey")), "");
        String operator = Objects.toString(condition.get("operator"), "equals");
        Object expected = condition.get("value");
        if ("in".equals(operator)) return stringList(expected).contains(current);
        boolean equals = current.equals(Objects.toString(expected, ""));
        return "not-equals".equals(operator) ? !equals : equals;
    }

    /** 按稳定申请编码裁剪表单；未配置适用范围的历史字段默认对全部申请展示。 */
    private List<Map<String, Object>> applicableFormSchema(
            List<Map<String, Object>> fields, String applicationCode) {
        return fields.stream()
                .filter(
                        field ->
                                !(applicationCode.startsWith("ACCOUNT_")
                                        && "operationType".equals(field.get("key"))))
                .filter(
                        field -> {
                            List<String> codes =
                                    stringList(field.get("applicableApplicationCodes"));
                            if (codes.isEmpty()
                                    && applicationCode.startsWith("ACCOUNT_")
                                    && hasOperationTypeCondition(field)) {
                                codes =
                                        LEGACY_ACCOUNT_FIELD_APPLICATIONS.getOrDefault(
                                                Objects.toString(field.get("key"), ""), List.of());
                            }
                            return codes.isEmpty() || codes.contains(applicationCode);
                        })
                .map(
                        field -> {
                            if (!applicationCode.startsWith("ACCOUNT_")
                                    || !hasOperationTypeCondition(field)) return field;
                            Map<String, Object> normalized = new LinkedHashMap<>(field);
                            normalized.remove("visibleWhen");
                            normalized.remove("requiredWhen");
                            String key = Objects.toString(field.get("key"), "");
                            boolean required =
                                    !"remark".equals(key)
                                            || "ACCOUNT_RECYCLE".equals(applicationCode);
                            normalized.put("required", required);
                            return normalized;
                        })
                .toList();
    }

    private boolean hasOperationTypeCondition(Map<String, Object> field) {
        return "operationType"
                        .equals(Objects.toString(map(field.get("visibleWhen")).get("fieldKey"), ""))
                || "operationType"
                        .equals(
                                Objects.toString(
                                        map(field.get("requiredWhen")).get("fieldKey"), ""));
    }

    /** 删除不适用于当前申请的字段值，防止调用方绕过页面隐藏规则注入数据。 */
    private void removeInapplicableValues(
            List<Map<String, Object>> completeFields,
            List<Map<String, Object>> applicableFields,
            Map<String, Object> data) {
        Set<String> applicableKeys =
                applicableFields.stream()
                        .map(field -> Objects.toString(field.get("key"), ""))
                        .collect(java.util.stream.Collectors.toSet());
        completeFields.stream()
                .map(field -> Objects.toString(field.get("key"), ""))
                .filter(key -> !key.isBlank() && !applicableKeys.contains(key))
                .forEach(data::remove);
    }

    private double decimal(Object value) {
        if (value instanceof Number number) return number.doubleValue();
        try {
            return Double.parseDouble(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    private List<String> stringList(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        return values.stream()
                .map(item -> Objects.toString(item, "").trim())
                .filter(item -> !item.isBlank())
                .distinct()
                .toList();
    }

    /** 复用旧 MPower 表单的入库口径：兼容中文标点，并移除列表条目前后空格。 */
    private void normalizeFormData(List<Map<String, Object>> fields, Map<String, Object> data) {
        for (Map<String, Object> field : fields) {
            if ("section".equals(field.get("type"))) continue;
            String key = Objects.toString(field.get("key"), "");
            Object value = data.get(key);
            if (value == null || value instanceof List<?>) continue;
            String rule = Objects.toString(field.get("validationRule"), "");
            String normalized = value.toString().replace('：', ':').replace('；', ';');
            if ("digit-list".equals(rule)) {
                data.put(
                        key,
                        Arrays.stream(normalized.split(";"))
                                .map(String::trim)
                                .filter(item -> !item.isBlank())
                                .collect(java.util.stream.Collectors.joining(";")));
            } else if ("pixel-list".equals(rule)) {
                data.put(
                        key,
                        Arrays.stream(normalized.split("[;\\n\\r]+"))
                                .map(String::trim)
                                .filter(item -> !item.isBlank())
                                .map(
                                        item ->
                                                Arrays.stream(item.split(":", -1))
                                                        .map(String::trim)
                                                        .collect(
                                                                java.util.stream.Collectors.joining(
                                                                        ":")))
                                .collect(java.util.stream.Collectors.joining(";")));
            }
        }
    }

    private boolean validDigitList(String value) {
        List<String> items =
                Arrays.stream(value.split(";"))
                        .map(String::trim)
                        .filter(item -> !item.isBlank())
                        .toList();
        return !items.isEmpty() && items.stream().allMatch(item -> item.matches("[0-9]+"));
    }

    static boolean validPixelList(String value) {
        String normalizedValue = value.replace('：', ':').replace('；', ';');
        List<String> items =
                Arrays.stream(normalizedValue.split("[;\\n\\r]+"))
                        .map(String::trim)
                        .filter(item -> !item.isBlank())
                        .toList();
        if (items.isEmpty()) return false;
        return items.stream()
                .allMatch(
                        item -> {
                            String[] parts = item.split(":", -1);
                            return parts.length == 2
                                    && !parts[0].trim().isBlank()
                                    && !parts[1].trim().isBlank();
                        });
    }

    private boolean isEmptyValue(Object value) {
        if (value == null) return true;
        if (value instanceof Collection<?> collection) return collection.isEmpty();
        return value.toString().isBlank();
    }

    private String configKey(String value) {
        String key = value.trim();
        if (!key.matches("[A-Za-z0-9_-]{1,24}")) throw validation("审批配置标识不合法");
        return key;
    }

    private String required(Map<String, Object> map, String key) {
        String value = Objects.toString(map.get(key), "").trim();
        if (value.isEmpty()) throw validation(key + "不能为空");
        return value;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Object value) {
        if (value instanceof List<?>) return (List<Map<String, Object>>) value;
        return (List<Map<String, Object>>) parse(value, List.of());
    }

    @SuppressWarnings("unchecked")
    /** 统一写入审批轨迹，避免控制器持有任何数据库访问实现。 */
    private void insertApprovalLog(
            Long applicationId,
            String action,
            Long actorId,
            String actorName,
            String remark,
            String actionData,
            Integer nodeIndex,
            String nodeName) {
        flowMapper.insertApprovalLog(
                params(
                        "applicationId",
                        applicationId,
                        "action",
                        action,
                        "actorId",
                        actorId,
                        "actorName",
                        actorName,
                        "remark",
                        remark,
                        "actionData",
                        actionData,
                        "nodeIndex",
                        nodeIndex,
                        "nodeName",
                        nodeName));
    }

    /** 按预期状态更新申请，状态条件可避免并发审批相互覆盖。 */
    private void updateApplication(
            Long id,
            String expectedStatus,
            String status,
            String remark,
            boolean decided,
            Integer nodeIndex,
            Long approverId,
            String approverName,
            Long operatorId) {
        flowMapper.updateApplication(
                params(
                        "id",
                        id,
                        "expectedStatus",
                        expectedStatus,
                        "status",
                        status,
                        "remark",
                        remark,
                        "decided",
                        decided,
                        "nodeIndex",
                        nodeIndex,
                        "approverId",
                        approverId,
                        "approverName",
                        approverName,
                        "operatorId",
                        operatorId));
    }

    /** 构造传递给 Mapper 的命名参数，允许可选字段使用 null。 */
    private Map<String, Object> params(Object... keyValues) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index < keyValues.length; index += 2) {
            result.put(Objects.toString(keyValues[index]), keyValues[index + 1]);
        }
        return result;
    }

    private Map<String, Object> map(Object value) {
        return value instanceof Map<?, ?> ? (Map<String, Object>) value : new LinkedHashMap<>();
    }

    /** 将审批人选择的资产 ID 转成有序去重列表，禁止无效或重复 ID 绕过数量校验。 */
    private List<Long> longList(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object item : values) {
            long id = number(item);
            if (id <= 0) throw validation("所选资产 ID 不合法");
            if (!ids.add(id)) throw validation("不能重复选择同一个资产");
        }
        return new ArrayList<>(ids);
    }

    private List<Long> applicationDefinitionIds(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object item : values) {
            long id = number(item);
            if (id <= 0) throw validation("关联申请 ID 不合法");
            ids.add(id);
        }
        return new ArrayList<>(ids);
    }

    private long number(Object value) {
        if (value instanceof Number n) return n.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "0"));
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private int intValue(Object value, int fallback) {
        long result = number(value);
        if (result <= 0) return fallback;
        try {
            return Math.toIntExact(result);
        } catch (ArithmeticException exception) {
            throw validation("数值超出允许范围");
        }
    }

    private String stringify(Object value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw validation("动态配置序列化失败");
        }
    }

    private Object parse(Object value, Object fallback) {
        if (value == null) return fallback;
        if (value instanceof List<?> || value instanceof Map<?, ?>) return value;
        try {
            return json.readValue(value.toString(), Object.class);
        } catch (JsonProcessingException exception) {
            return fallback;
        }
    }

    private BusinessException validation(String message) {
        return new BusinessException(422, message);
    }

    private BusinessException conflict(String message) {
        return new BusinessException(409, message);
    }

    private BusinessException notFound(String message) {
        return new BusinessException(404, message + "不存在");
    }
}
