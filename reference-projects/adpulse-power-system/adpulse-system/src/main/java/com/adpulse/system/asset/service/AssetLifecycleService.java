package com.adpulse.system.asset.service;

import com.adpulse.system.asset.dto.AssetViews;
import com.adpulse.system.asset.lifecycle.AssetLifecycleEvent;
import com.adpulse.system.asset.mapper.AssetLifecycleMapper;
import com.adpulse.system.asset.model.MediaAsset;
import com.adpulse.system.asset.model.MediaAssetLifecycleEvent;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;

/** 维护普通库存资产的事件账本，并生成不含敏感明细的只读生命周期视图。 */
@Service
public class AssetLifecycleService {
    private static final ObjectMapper JSON_MAPPER = new ObjectMapper();
    private final AssetLifecycleMapper mapper;

    public AssetLifecycleService(AssetLifecycleMapper mapper) {
        this.mapper = mapper;
    }

    public void record(String eventType, MediaAsset asset, String description) {
        record(eventType, asset, description, null, List.of());
    }

    public void record(
            String eventType,
            MediaAsset asset,
            String description,
            String updateSource,
            List<AssetViews.LifecycleFieldChange> changes) {
        CurrentUser actor = SecurityContextHelper.currentUser();
        record(
                eventType,
                asset.getId(),
                asset.getStatus(),
                asset.getApplicationId(),
                actor.userId(),
                actor.displayName(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                asset.getUsageTeam() == null || asset.getUsageTeam().isBlank()
                        ? asset.getAssigneeDepartmentName()
                        : asset.getUsageTeam(),
                description,
                updateSource,
                changes);
    }

    /** 回收模块使用快照字段记账，避免该模块读取或暴露资产凭据。 */
    public void record(
            String eventType,
            Long assetId,
            String status,
            Long applicationId,
            Long actorId,
            String actorName,
            Long usageUserId,
            String usageUserName,
            String projectName,
            String teamName,
            String description) {
        record(
                eventType,
                assetId,
                status,
                applicationId,
                actorId,
                actorName,
                usageUserId,
                usageUserName,
                projectName,
                teamName,
                description,
                null,
                List.of());
    }

    public void record(
            String eventType,
            Long assetId,
            String status,
            Long applicationId,
            Long actorId,
            String actorName,
            Long usageUserId,
            String usageUserName,
            String projectName,
            String teamName,
            String description,
            String updateSource,
            List<AssetViews.LifecycleFieldChange> changes) {
        MediaAssetLifecycleEvent event = new MediaAssetLifecycleEvent();
        event.setAssetId(assetId);
        event.setEventType(eventType);
        event.setStatus(status);
        event.setApplicationId(applicationId);
        event.setActorId(actorId);
        event.setActorName(actorName);
        event.setUsageUserId(usageUserId);
        event.setUsageUserName(usageUserName);
        event.setProjectName(projectName);
        event.setTeamName(teamName);
        event.setDescription(description);
        event.setUpdateSource(updateSource);
        if (changes != null && !changes.isEmpty()) {
            try {
                event.setChangesJson(JSON_MAPPER.writeValueAsString(changes));
            } catch (Exception exception) {
                throw new IllegalStateException("生命周期资料快照序列化失败", exception);
            }
        }
        event.setOccurredAt(LocalDateTime.now());
        mapper.insert(event);
    }

    public AssetViews.AssetLifecycleDetail detail(MediaAsset asset) {
        List<MediaAssetLifecycleEvent> persisted = mapper.findByAssetId(asset.getId());
        List<MediaAssetLifecycleEvent> events = new ArrayList<>(persisted);
        if (events.stream().noneMatch(event -> "STOCKED".equals(event.getEventType()))) {
            MediaAssetLifecycleEvent stocked = new MediaAssetLifecycleEvent();
            stocked.setId(0L);
            stocked.setEventType("STOCKED");
            stocked.setStatus(asset.getStatus());
            stocked.setActorName("系统");
            stocked.setDescription("历史入库快照");
            stocked.setOccurredAt(asset.getCreatedAt());
            events.add(stocked);
        }
        List<AssetLifecycleEvent> usageEvents =
                events.stream()
                        .filter(
                                event ->
                                        "ASSIGNED".equals(event.getEventType())
                                                || "RELEASED".equals(event.getEventType()))
                        .map(
                                event ->
                                        AssetLifecycleEvent.usage(
                                                event.getEventType(),
                                                String.valueOf(event.getUsageUserId()),
                                                event.getUsageUserName(),
                                                event.getOccurredAt()))
                        .toList();
        List<AssetViews.LifecycleUsagePeriod> periods =
                AssetLifecycleTimeline.usagePeriods(usageEvents).stream()
                        .map(
                                period ->
                                        new AssetViews.LifecycleUsagePeriod(
                                                period.userId(),
                                                period.userName(),
                                                period.startedAt(),
                                                period.endedAt(),
                                                period.status(),
                                                null,
                                                asset.getProjectName(),
                                                asset.getUsageTeam() == null
                                                                || asset.getUsageTeam().isBlank()
                                                        ? asset.getAssigneeDepartmentName()
                                                        : asset.getUsageTeam()))
                        .toList();
        List<AssetViews.LifecycleEvent> timeline =
                events.stream()
                        .sorted(
                                (left, right) ->
                                        right.getOccurredAt().compareTo(left.getOccurredAt()))
                        .map(
                                event ->
                                        new AssetViews.LifecycleEvent(
                                                String.valueOf(event.getId()),
                                                event.getEventType(),
                                                event.getStatus(),
                                                event.getActorName(),
                                                event.getDescription(),
                                                event.getApplicationId() == null
                                                        ? null
                                                        : String.valueOf(event.getApplicationId()),
                                                event.getProjectName(),
                                                event.getTeamName(),
                                                event.getOccurredAt(),
                                                event.getUpdateSource(),
                                                readChanges(event.getChangesJson())))
                        .toList();
        return new AssetViews.AssetLifecycleDetail(
                new AssetViews.LifecycleAsset(
                        String.valueOf(asset.getId()),
                        asset.getAssetType(),
                        asset.getAssetName(),
                        asset.getAssetCode(),
                        asset.getStatus(),
                        asset.getUsageUserNames() == null
                                ? asset.getAssigneeName()
                                : asset.getUsageUserNames(),
                        asset.getProjectName(),
                        asset.getUsageTeam() == null || asset.getUsageTeam().isBlank()
                                ? asset.getAssigneeDepartmentName()
                                : asset.getUsageTeam()),
                periods,
                timeline);
    }

    private List<AssetViews.LifecycleFieldChange> readChanges(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return JSON_MAPPER.readValue(
                    json, new TypeReference<List<AssetViews.LifecycleFieldChange>>() {});
        } catch (Exception ignored) {
            return List.of();
        }
    }
}
