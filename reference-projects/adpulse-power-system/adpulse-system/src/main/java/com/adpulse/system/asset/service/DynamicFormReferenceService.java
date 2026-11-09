package com.adpulse.system.asset.service;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import java.util.*;
import org.springframework.stereotype.Service;

/** 动态审批表单的系统下拉引用校验与名称快照服务。 */
@Service
public class DynamicFormReferenceService {
    private static final Set<String> SYSTEM_OPTION_SOURCES =
            Set.of("ad-accounts", "channels", "departments", "projects", "roles", "users");

    private final DynamicAssetFlowMapper flowMapper;

    public DynamicFormReferenceService(DynamicAssetFlowMapper flowMapper) {
        this.flowMapper = flowMapper;
    }

    /**
     * 校验系统下拉提交的稳定 ID，并用数据库当前名称覆盖前端同名快照字段。
     *
     * @param fields 已发布的表单结构
     * @param data 本次申请数据
     */
    public void enrichSystemOptionSnapshots(
            List<Map<String, Object>> fields, Map<String, Object> data) {
        for (Map<String, Object> field : fields) {
            String type = Objects.toString(field.get("type"), "");
            if ("section".equals(type)) continue;
            if (field.get("visibleWhen") != null
                    && !conditionMatches(field.get("visibleWhen"), data)) continue;
            if (!Set.of("select", "multi-select").contains(type)) continue;
            String source = Objects.toString(field.get("optionSource"), "custom");
            if ("custom".equals(source)) continue;
            if (!SYSTEM_OPTION_SOURCES.contains(source)) {
                throw BusinessException.validation("不支持的下拉选项来源：" + source);
            }
            String key = Objects.toString(field.get("key"), "");
            Object selected = data.get(key);
            if (isEmptyValue(selected)) continue;
            String snapshotBase =
                    key.endsWith("Ids")
                            ? key.substring(0, key.length() - 3)
                            : key.endsWith("Id") ? key.substring(0, key.length() - 2) : key;
            String snapshotKey = snapshotBase + ("multi-select".equals(type) ? "Names" : "Name");
            List<String> selectedIds =
                    selected instanceof List<?>
                            ? stringList(selected)
                            : List.of(selected.toString());
            if ("ad-accounts".equals(source)) {
                selectedIds =
                        selectedIds.stream()
                                .map(id -> normalizeAdAccountId(id, field.get("label")))
                                .distinct()
                                .toList();
                data.put(key, "multi-select".equals(type) ? selectedIds : selectedIds.get(0));
            }
            List<String> labels =
                    "ad-accounts".equals(source)
                            ? resolveAdAccountLabels(
                                    selectedIds, data.get(snapshotKey), field.get("label"))
                            : selectedIds.stream()
                                    .map(
                                            id ->
                                                    resolveSystemOptionLabel(
                                                            source, id, field.get("label")))
                                    .toList();
            data.put(snapshotKey, "multi-select".equals(type) ? labels : labels.get(0));
        }
    }

    /**
     * 广告账户下拉来自 MPower 实时账户管理，而本服务的本地账户表并非完整镜像。优先使用本地名称； 本地尚未同步该账户时，校验前端随选项提交的 ID
     * 快照后保留展示名称，避免把真实账户误判为不存在。
     */
    private List<String> resolveAdAccountLabels(
            List<String> selectedIds, Object submittedSnapshots, Object fieldLabel) {
        List<String> snapshots = stringList(submittedSnapshots);
        List<String> labels = new ArrayList<>(selectedIds.size());
        for (int index = 0; index < selectedIds.size(); index++) {
            String id = selectedIds.get(index);
            List<String> localLabels = flowMapper.findActiveAccountLabels(id);
            if (localLabels.size() == 1
                    && localLabels.get(0) != null
                    && !localLabels.get(0).isBlank()) {
                labels.add(localLabels.get(0));
                continue;
            }
            String snapshot = index < snapshots.size() ? snapshots.get(index) : "";
            if (!snapshotContainsAccountId(snapshot, id)) {
                throw BusinessException.validation(fieldLabel + "包含已停用或不存在的选项，请重新选择");
            }
            labels.add(snapshot);
        }
        return labels;
    }

    private String resolveSystemOptionLabel(String source, String idValue, Object fieldLabel) {
        long id = number(idValue);
        if (id <= 0) throw BusinessException.validation(fieldLabel + "包含无效选项，请重新选择");
        if (!Set.of("channels", "departments", "projects", "roles", "users").contains(source)) {
            throw BusinessException.validation("不支持的下拉选项来源：" + source);
        }
        List<String> labels = flowMapper.findActiveReferenceLabels(source, id);
        return requireSingleActiveLabel(labels, fieldLabel);
    }

    /** 将 Meta 的 act_xxx 展示格式转为账户库使用的纯数字稳定 ID。 */
    private String normalizeAdAccountId(String value, Object fieldLabel) {
        String normalized = Objects.toString(value, "").trim().replaceFirst("(?i)^act_", "");
        if (!normalized.matches("\\d+")) {
            throw BusinessException.validation(fieldLabel + "包含无效选项，请重新选择");
        }
        return normalized;
    }

    private boolean snapshotContainsAccountId(String snapshot, String accountId) {
        return Arrays.stream(snapshot.split("[·\\s]+"))
                .map(value -> value.trim().replaceFirst("(?i)^act_", ""))
                .anyMatch(accountId::equals);
    }

    private String requireSingleActiveLabel(List<String> labels, Object fieldLabel) {
        if (labels.size() != 1 || labels.get(0) == null || labels.get(0).isBlank()) {
            throw BusinessException.validation(fieldLabel + "包含已停用或不存在的选项，请重新选择");
        }
        return labels.get(0);
    }

    private boolean conditionMatches(Object value, Map<String, Object> data) {
        if (!(value instanceof Map<?, ?> rawCondition)) return false;
        Map<String, Object> condition = new LinkedHashMap<>();
        rawCondition.forEach((key, item) -> condition.put(Objects.toString(key, ""), item));
        String current = Objects.toString(data.get(condition.get("fieldKey")), "");
        String operator = Objects.toString(condition.get("operator"), "equals");
        Object expected = condition.get("value");
        if ("in".equals(operator)) return stringList(expected).contains(current);
        boolean equals = current.equals(Objects.toString(expected, ""));
        return "not-equals".equals(operator) ? !equals : equals;
    }

    private boolean isEmptyValue(Object value) {
        if (value == null) return true;
        if (value instanceof Collection<?> collection) return collection.isEmpty();
        return value.toString().trim().isEmpty();
    }

    private List<String> stringList(Object value) {
        if (!(value instanceof List<?> values)) return List.of();
        return values.stream()
                .map(item -> Objects.toString(item, "").trim())
                .filter(item -> !item.isBlank())
                .distinct()
                .toList();
    }

    private long number(Object value) {
        if (value instanceof Number number) return number.longValue();
        try {
            return Long.parseLong(Objects.toString(value, "0"));
        } catch (NumberFormatException exception) {
            return 0;
        }
    }
}
