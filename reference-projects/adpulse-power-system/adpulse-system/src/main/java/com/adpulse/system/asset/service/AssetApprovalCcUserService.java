package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;

/** 按申请快照中的稳定用户 ID 解析审批抄送人，只负责读模型展示，不触发通知或流程日志。 */
@Service
public class AssetApprovalCcUserService {
    private final DynamicAssetFlowMapper flowMapper;
    private final ObjectMapper json;

    public AssetApprovalCcUserService(DynamicAssetFlowMapper flowMapper, ObjectMapper json) {
        this.flowMapper = flowMapper;
        this.json = json;
    }

    /** 为已解码的申请详情批量补齐抄送人，兼容普通申请和迁移历史快照。 */
    public void enrichApplications(List<Map<String, Object>> applications) {
        List<Object> rawCcUserIds =
                applications.stream()
                        .map(application -> map(application.get("formData")).get("_ccUserIds"))
                        .toList();
        List<List<AssetViews.ApprovalCcUser>> resolvedUsers = resolveAll(rawCcUserIds);
        for (int index = 0; index < applications.size(); index++) {
            applications.get(index).put("ccUsers", resolvedUsers.get(index));
        }
    }

    /**
     * 批量解析多张申请的抄送用户，保持每张申请中的原始 ID 顺序并去重。
     *
     * <p>停用但未删除的用户仍返回原姓名；缺失、软删除等无法解析的历史 ID 返回明确占位，避免 页面错误显示为“无人抄送”。
     */
    public List<List<AssetViews.ApprovalCcUser>> resolveAll(List<?> rawValues) {
        List<List<Long>> applicationUserIds = rawValues.stream().map(this::parseUserIds).toList();
        List<Long> allUserIds =
                applicationUserIds.stream().flatMap(Collection::stream).distinct().toList();
        Map<Long, AssetViews.ApprovalCcUser> usersById = new LinkedHashMap<>();
        if (!allUserIds.isEmpty()) {
            flowMapper
                    .findApprovalCcUsersByIds(allUserIds)
                    .forEach(
                            user -> {
                                long id = number(user.get("id"));
                                if (id <= 0) return;
                                usersById.put(
                                        id,
                                        new AssetViews.ApprovalCcUser(
                                                Long.toString(id),
                                                Objects.toString(
                                                                user.get("displayName"), "用户 " + id)
                                                        .trim(),
                                                number(user.get("status")) == 1,
                                                true));
                            });
        }

        return applicationUserIds.stream()
                .map(
                        ids ->
                                ids.stream()
                                        .map(
                                                id ->
                                                        usersById.getOrDefault(
                                                                id,
                                                                new AssetViews.ApprovalCcUser(
                                                                        Long.toString(id),
                                                                        "用户 " + id,
                                                                        false,
                                                                        false)))
                                        .toList())
                .toList();
    }

    private List<Long> parseUserIds(Object value) {
        if (value == null) return List.of();
        if (value instanceof Collection<?> collection) return validIds(collection);
        if (value instanceof Number) return validIds(List.of(value));

        String text = Objects.toString(value, "").trim();
        if (text.isEmpty()) return List.of();
        if (text.startsWith("[") && text.endsWith("]")) {
            try {
                return validIds(json.readValue(text, List.class));
            } catch (JsonProcessingException ignored) {
                return List.of();
            }
        }
        return validIds(List.of(text.split(",")));
    }

    private List<Long> validIds(Collection<?> values) {
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object value : values) {
            long id = number(value);
            if (id > 0) ids.add(id);
        }
        return new ArrayList<>(ids);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map<?, ?> ? (Map<String, Object>) value : Map.of();
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "").trim());
        } catch (NumberFormatException exception) {
            return 0;
        }
    }
}
