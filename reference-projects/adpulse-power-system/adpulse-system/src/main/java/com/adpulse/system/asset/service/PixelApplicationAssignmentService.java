package com.adpulse.system.asset.service;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;

/** 像素申请在提交和最终审批阶段使用的统一选择校验与项目分配服务。 */
@Service
public class PixelApplicationAssignmentService {
    public static final String COMPLETION_MODE = "pixel-auto-assign";
    public static final String COMPLETION_MODE_KEY = "_completionMode";
    public static final String PIXEL_IDS_KEY = "pixelAssetIds";

    private final DynamicAssetFlowMapper flowMapper;
    private final AssetService assetService;
    private final ObjectMapper json;

    public PixelApplicationAssignmentService(
            DynamicAssetFlowMapper flowMapper, AssetService assetService, ObjectMapper json) {
        this.flowMapper = flowMapper;
        this.assetService = assetService;
        this.json = json;
    }

    /** 提交申请时校验所选像素并用服务端资产信息生成名称快照；此阶段不预占库存。 */
    public int validateAndEnrichSelection(Map<String, Object> formData) {
        List<Long> selectedIds = selectedPixelIds(formData);
        List<Map<String, Object>> assets = flowMapper.lockAssets(selectedIds);
        validateAvailablePixels(selectedIds, assets);

        Map<Long, Map<String, Object>> assetsById = new LinkedHashMap<>();
        assets.forEach(asset -> assetsById.put(number(asset.get("id")), asset));
        List<String> labels =
                selectedIds.stream().map(id -> pixelLabel(assetsById.get(id))).toList();
        formData.put(PIXEL_IDS_KEY, selectedIds.stream().map(String::valueOf).toList());
        formData.put("pixelAssetNames", labels);
        return selectedIds.size();
    }

    /** 最终审批通过时重新锁定并校验像素，然后原子写入所属项目和使用团队。 */
    public void assignSelectedPixels(Map<String, Object> application, long operatorId) {
        Map<String, Object> formData = objectMap(application.get("formData"));
        List<Long> selectedIds = selectedPixelIds(formData);
        List<Map<String, Object>> assets = flowMapper.lockAssets(selectedIds);
        validateAvailablePixels(selectedIds, assets);

        String projectId = required(formData, "projectId", "像素申请缺少所属项目");
        String projectName = required(formData, "projectName", "像素申请缺少所属项目名称");
        required(formData, "usageTeamId", "像素申请缺少使用团队");
        String usageTeam = required(formData, "usageTeamName", "像素申请缺少使用团队名称");

        for (Map<String, Object> asset : assets) {
            long assetId = number(asset.get("id"));
            Map<String, Object> assignment = new LinkedHashMap<>();
            assignment.put("applicationId", application.get("id"));
            assignment.put("projectId", projectId);
            assignment.put("projectName", projectName);
            assignment.put("usageTeam", usageTeam);
            assignment.put("operatorId", operatorId);
            assignment.put("assetId", assetId);
            if (flowMapper.assignPixelAsset(assignment) != 1) {
                throw BusinessException.conflict("所选像素状态已变化，请刷新后重新选择");
            }
            assetService.recordLifecycleAllocation(assetId);
        }
    }

    public boolean isPixelAutoAssignment(Map<String, Object> application) {
        return COMPLETION_MODE.equals(
                Objects.toString(
                        objectMap(application.get("formData")).get(COMPLETION_MODE_KEY), ""));
    }

    private List<Long> selectedPixelIds(Map<String, Object> formData) {
        Object value = formData.get(PIXEL_IDS_KEY);
        if (!(value instanceof List<?> values) || values.isEmpty()) {
            throw BusinessException.validation("请选择至少一个像素");
        }
        LinkedHashSet<Long> ids = new LinkedHashSet<>();
        for (Object item : values) {
            long id = number(item);
            if (id <= 0 || !ids.add(id)) {
                throw BusinessException.validation("所选像素标识不合法或存在重复");
            }
        }
        return new ArrayList<>(ids);
    }

    private void validateAvailablePixels(List<Long> selectedIds, List<Map<String, Object>> assets) {
        Map<Long, Map<String, Object>> assetsById = new LinkedHashMap<>();
        assets.forEach(asset -> assetsById.put(number(asset.get("id")), asset));
        List<String> invalid =
                selectedIds.stream()
                        .filter(
                                id -> {
                                    Map<String, Object> asset = assetsById.get(id);
                                    return asset == null
                                            || !"PIXEL"
                                                    .equals(
                                                            Objects.toString(
                                                                    asset.get("assetType"), ""))
                                            || !"AVAILABLE"
                                                    .equals(
                                                            Objects.toString(
                                                                    asset.get("status"), ""));
                                })
                        .limit(5)
                        .map(
                                id -> {
                                    Map<String, Object> asset = assetsById.get(id);
                                    return asset == null ? String.valueOf(id) : pixelLabel(asset);
                                })
                        .toList();
        if (!invalid.isEmpty() || assets.size() != selectedIds.size()) {
            throw BusinessException.conflict(
                    "以下像素不存在或已被分配：" + String.join("、", invalid) + "，请重新选择");
        }
    }

    private String pixelLabel(Map<String, Object> asset) {
        if (asset == null) return "未知像素";
        String name = Objects.toString(asset.get("assetName"), "").trim();
        String code = Objects.toString(asset.get("assetCode"), "").trim();
        if (name.isBlank()) return code.isBlank() ? String.valueOf(asset.get("id")) : code;
        return code.isBlank() ? name : name + "（" + code + "）";
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object value) {
        if (value instanceof Map<?, ?>) return (Map<String, Object>) value;
        try {
            return json.readValue(Objects.toString(value, "{}"), Map.class);
        } catch (JsonProcessingException exception) {
            throw BusinessException.conflict("像素申请数据损坏");
        }
    }

    private String required(Map<String, Object> data, String key, String message) {
        String value = Objects.toString(data.get(key), "").trim();
        if (value.isBlank()) throw BusinessException.validation(message);
        return value;
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
