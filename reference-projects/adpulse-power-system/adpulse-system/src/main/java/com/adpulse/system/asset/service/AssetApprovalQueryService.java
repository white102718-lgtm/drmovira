package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Service;

/** 审批中心列表的权限筛选、服务端分页和轻量筛选元数据查询。 */
@Service
public class AssetApprovalQueryService {
    private static final int DEFAULT_PAGE_SIZE = 10;
    private static final int MAX_PAGE_SIZE = 500;
    private static final int MAX_KEYWORD_LENGTH = 100;
    private static final Set<String> QUEUES =
            Set.of("pending", "handling", "processed", "copied", "initiated");
    private static final Set<String> DECISION_RESULTS = Set.of("APPROVED", "REJECTED");

    private final DynamicAssetFlowMapper flowMapper;
    private final AssetApprovalCcUserService ccUserService;

    public AssetApprovalQueryService(
            DynamicAssetFlowMapper flowMapper, AssetApprovalCcUserService ccUserService) {
        this.flowMapper = flowMapper;
        this.ccUserService = ccUserService;
    }

    /** 查询当前用户在指定审批队列中的一页轻量摘要。 */
    public PageData page(Query query) {
        Map<String, Object> parameters = validatedParameters(query);
        List<Map<String, Object>> rows = flowMapper.findApprovalPage(parameters);
        List<List<AssetViews.ApprovalCcUser>> ccUsers =
                ccUserService.resolveAll(rows.stream().map(row -> row.get("ccUserIds")).toList());
        List<AssetViews.ApprovalListItem> items = new ArrayList<>(rows.size());
        for (int index = 0; index < rows.size(); index++) {
            items.add(toListItem(rows.get(index), ccUsers.get(index)));
        }
        long total = flowMapper.countApprovalPage(parameters);
        int page = (int) parameters.get("page");
        int pageSize = (int) parameters.get("pageSize");
        boolean hasMore = (long) page * pageSize < total;
        return new PageData(items, total, page, pageSize, hasMore);
    }

    /** 返回当前用户可见队列总数及部门、申请人筛选选项，不读取完整申请单。 */
    public AssetViews.ApprovalMetadata metadata() {
        long userId = SecurityContextHelper.currentUserId();
        AssetViews.ApprovalQueueCounts counts =
                new AssetViews.ApprovalQueueCounts(
                        countQueue(userId, "pending"),
                        countQueue(userId, "handling"),
                        countQueue(userId, "processed"),
                        countQueue(userId, "copied"),
                        countQueue(userId, "initiated"));
        Map<String, Object> visibilityQuery = emptyParameters(userId, "pending");
        return new AssetViews.ApprovalMetadata(
                counts,
                options(flowMapper.findApprovalDepartments(visibilityQuery)),
                options(flowMapper.findApprovalRequesters(visibilityQuery)));
    }

    private long countQueue(long userId, String queue) {
        Map<String, Object> query = emptyParameters(userId, queue);
        return flowMapper.countApprovalPage(query);
    }

    private Map<String, Object> validatedParameters(Query query) {
        String queue = normalize(query.queue()).toLowerCase(Locale.ROOT);
        if (!QUEUES.contains(queue)) throw BusinessException.validation("不支持的审批队列");
        int page = query.page() == null ? 1 : query.page();
        int pageSize = query.pageSize() == null ? DEFAULT_PAGE_SIZE : query.pageSize();
        if (page < 1) throw BusinessException.validation("页码必须大于等于 1");
        if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
            throw BusinessException.validation("每页条数必须在 1 到 500 之间");
        }
        String keyword = normalize(query.keyword());
        if (keyword.length() > MAX_KEYWORD_LENGTH) {
            throw BusinessException.validation("搜索关键词不能超过 100 个字符");
        }
        Long applicationDefinitionId = positiveId(query.applicationDefinitionId(), "申请类型");
        Long departmentId = positiveId(query.departmentId(), "所属部门");
        Long requesterId = positiveId(query.requesterId(), "申请人");
        String decisionResult = normalize(query.decisionResult()).toUpperCase(Locale.ROOT);
        if (!decisionResult.isEmpty() && !DECISION_RESULTS.contains(decisionResult)) {
            throw BusinessException.validation("不支持的审批结果");
        }
        if (!"processed".equals(queue)) decisionResult = "";
        int offset;
        try {
            offset = Math.multiplyExact(page - 1, pageSize);
        } catch (ArithmeticException exception) {
            throw BusinessException.validation("页码超出可查询范围");
        }

        Map<String, Object> parameters =
                emptyParameters(SecurityContextHelper.currentUserId(), queue);
        parameters.put("page", page);
        parameters.put("pageSize", pageSize);
        parameters.put("offset", offset);
        parameters.put("keyword", keyword);
        parameters.put("applicationDefinitionId", applicationDefinitionId);
        parameters.put("assetType", normalize(query.assetType()).toUpperCase(Locale.ROOT));
        parameters.put("departmentId", departmentId);
        parameters.put("requesterId", requesterId);
        parameters.put("decisionResult", decisionResult);
        return parameters;
    }

    private Map<String, Object> emptyParameters(long userId, String queue) {
        Map<String, Object> parameters = new LinkedHashMap<>();
        parameters.put("userId", userId);
        parameters.put("queue", queue);
        parameters.put("page", 1);
        parameters.put("pageSize", DEFAULT_PAGE_SIZE);
        parameters.put("offset", 0);
        parameters.put("keyword", "");
        parameters.put("applicationDefinitionId", null);
        parameters.put("assetType", "");
        parameters.put("departmentId", null);
        parameters.put("requesterId", null);
        parameters.put("decisionResult", "");
        return parameters;
    }

    private Long positiveId(Long value, String label) {
        if (value == null) return null;
        if (value <= 0) throw BusinessException.validation(label + "无效");
        return value;
    }

    private AssetViews.ApprovalListItem toListItem(
            Map<String, Object> row, List<AssetViews.ApprovalCcUser> ccUsers) {
        return new AssetViews.ApprovalListItem(
                text(row.get("id")),
                text(row.get("applicationNo")),
                text(row.get("applicationDefinitionId")),
                text(row.get("assetType")),
                text(row.get("configCategory")),
                text(row.get("title")),
                (int) number(row.get("quantity")),
                text(row.get("reason")),
                text(row.get("status")),
                text(row.get("requesterId")),
                text(row.get("requesterName")),
                text(row.get("approverId")),
                text(row.get("approverName")),
                text(row.get("departmentId")),
                text(row.get("departmentName")),
                text(row.get("projectName")),
                ccUsers,
                (java.time.LocalDateTime) row.get("createdAt"),
                (java.time.LocalDateTime) row.get("updatedAt"));
    }

    private List<AssetViews.ApprovalFilterOption> options(List<Map<String, Object>> rows) {
        List<AssetViews.ApprovalFilterOption> options = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            String value = Objects.toString(row.get("value"), "").trim();
            String label = Objects.toString(row.get("label"), "").trim();
            if (!value.isEmpty() && !label.isEmpty()) {
                options.add(new AssetViews.ApprovalFilterOption(value, label));
            }
        }
        return options;
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }

    private String normalize(String value) {
        return Objects.toString(value, "").trim();
    }

    private String text(Object value) {
        return Objects.toString(value, "");
    }

    /** 审批中心分页查询条件；所有 ID 都以稳定数据库 ID 过滤。 */
    public record Query(
            String queue,
            Integer page,
            Integer pageSize,
            String keyword,
            Long applicationDefinitionId,
            String assetType,
            Long departmentId,
            Long requesterId,
            String decisionResult) {}

    /** 查询层返回给控制器的分页数据。 */
    public record PageData(
            List<AssetViews.ApprovalListItem> items,
            long total,
            int page,
            int pageSize,
            boolean hasMore) {}
}
