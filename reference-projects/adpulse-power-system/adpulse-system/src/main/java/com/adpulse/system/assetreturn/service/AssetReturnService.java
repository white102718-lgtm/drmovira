package com.adpulse.system.assetreturn.service;

import com.adpulse.system.asset.service.AssetLifecycleService;
import com.adpulse.system.assetreturn.dto.AssetReturnRequests;
import com.adpulse.system.assetreturn.mapper.AssetReturnMapper;
import com.adpulse.system.assetreturn.model.AssetReturn;
import com.adpulse.system.assetreturn.model.AssetReturnSummary;
import com.adpulse.system.assetreturn.model.ReturnableAsset;
import com.adpulse.system.common.api.PageResult;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.common.security.SecurityContextHelper;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 资产回收申请、状态流转与并发保护。 */
@Service
public class AssetReturnService {
    public static final String MANAGE_AUTHORITY = "media:resource:return:manage";

    private static final String STATUS_ASSIGNED = "ASSIGNED";
    private static final String STATUS_PENDING = "PENDING";
    private static final String STATUS_COMPLETED = "COMPLETED";
    private static final String ASSET_STATUS_RETURN_PENDING = "RETURN_PENDING";
    private static final Set<String> ASSET_TYPES =
            Set.of(
                    "BM",
                    "COMPUTER",
                    "EMAIL",
                    "MOBILE",
                    "PAGE",
                    "PERSONAL",
                    "PIXEL",
                    "STATIC_IP",
                    "TG");
    private static final Set<String> PERSONAL_ASSET_SUBTYPES = Set.of("fb", "wechat");
    private static final Set<String> OUTCOMES = Set.of("AVAILABLE", "DISABLED");
    private static final DateTimeFormatter RETURN_NO_TIME =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmssSSS");

    private final AssetReturnMapper mapper;
    private final AssetLifecycleService lifecycleService;

    public AssetReturnService(AssetReturnMapper mapper, AssetLifecycleService lifecycleService) {
        this.mapper = mapper;
        this.lifecycleService = lifecycleService;
    }

    /** 分页查询回收单，由接口层限制为资源管理人员访问。 */
    public PageResult<AssetReturn> page(
            String keyword,
            String status,
            String assetType,
            String assetSubtype,
            int page,
            int pageSize) {
        int safePage = Math.max(page, 1);
        int safeSize = Math.min(Math.max(pageSize, 1), 200);
        String normalizedKeyword = textOrNull(keyword);
        String normalizedStatus = statusOrNull(status);
        String normalizedAssetType = assetTypeOrNull(assetType);
        String normalizedAssetSubtype = assetSubtypeOrNull(normalizedAssetType, assetSubtype);
        long total =
                mapper.countReturns(
                        normalizedKeyword,
                        normalizedStatus,
                        normalizedAssetType,
                        normalizedAssetSubtype);
        return new PageResult<>(
                mapper.findReturns(
                        normalizedKeyword,
                        normalizedStatus,
                        normalizedAssetType,
                        normalizedAssetSubtype,
                        (safePage - 1) * safeSize,
                        safeSize),
                total,
                safePage,
                safeSize);
    }

    /** 统计待处理、已完成与全部回收单数量。 */
    public AssetReturnSummary summary() {
        long pending = mapper.countReturns(null, STATUS_PENDING, null, null);
        long completed = mapper.countReturns(null, STATUS_COMPLETED, null, null);
        return new AssetReturnSummary(pending, completed, pending + completed);
    }

    /**
     * 为已分配资产发起回收。
     *
     * <p>资产行在事务内加锁，保证同一资产不会生成两张待处理回收单。普通用户只能回收自己的资产，资源管理人员可代为发起。
     */
    @Transactional
    public AssetReturn create(Long assetId, AssetReturnRequests.Create request) {
        CurrentUser user = SecurityContextHelper.currentUser();
        ReturnableAsset asset = mapper.lockAsset(assetId);
        if (asset == null) throw BusinessException.notFound("资产");
        if (!STATUS_ASSIGNED.equals(asset.getStatus())) {
            throw BusinessException.conflict("仅已分配资产可发起回收");
        }
        if (!user.userId().equals(asset.getAssigneeId()) && !canManage(user)) {
            throw BusinessException.conflict("只能回收分配给自己的资产");
        }

        AssetReturn assetReturn = snapshot(asset, request.reason().trim(), user);
        mapper.insertReturn(assetReturn);
        if (mapper.markAssetReturnPending(assetId, user.userId()) != 1) {
            throw BusinessException.conflict("资产状态已变化，请刷新后重试");
        }
        lifecycleService.record(
                "RETURN_REQUESTED",
                asset.getId(),
                ASSET_STATUS_RETURN_PENDING,
                asset.getApplicationId(),
                user.userId(),
                user.displayName(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                null,
                "已提交资产回收申请");
        return mapper.findReturn(assetReturn.getId());
    }

    /** 完成回收，并原子解除使用人与来源申请绑定。 */
    @Transactional
    public AssetReturn complete(Long id, AssetReturnRequests.Complete request) {
        String outcome = normalizeOutcome(request.outcome());
        AssetReturn assetReturn = mapper.lockReturn(id);
        if (assetReturn == null) throw BusinessException.notFound("回收申请");
        if (!STATUS_PENDING.equals(assetReturn.getStatus())) {
            throw BusinessException.conflict("该回收申请已处理");
        }
        ReturnableAsset asset = mapper.lockAsset(assetReturn.getAssetId());
        if (asset == null) throw BusinessException.conflict("回收申请关联的资产不存在");
        if (!ASSET_STATUS_RETURN_PENDING.equals(asset.getStatus())) {
            throw BusinessException.conflict("资产已不在待回收状态，请刷新后核对");
        }

        CurrentUser user = SecurityContextHelper.currentUser();
        if (mapper.completeReturn(id, outcome, user.userId(), user.displayName()) != 1
                || mapper.releaseAsset(asset.getId(), outcome, user.userId()) != 1) {
            throw BusinessException.conflict("回收状态已变化，请刷新后重试");
        }
        lifecycleService.record(
                "RELEASED",
                asset.getId(),
                outcome,
                assetReturn.getApplicationId(),
                user.userId(),
                user.displayName(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                null,
                "资产回收完成，使用区间结束");
        lifecycleService.record(
                "RETURN_COMPLETED",
                asset.getId(),
                outcome,
                assetReturn.getApplicationId(),
                user.userId(),
                user.displayName(),
                asset.getAssigneeId(),
                asset.getAssigneeName(),
                asset.getProjectName(),
                null,
                "DISABLED".equals(outcome) ? "回收完成并停用资产" : "回收完成并重新入库");
        return mapper.findReturn(id);
    }

    private AssetReturn snapshot(ReturnableAsset asset, String reason, CurrentUser user) {
        AssetReturn value = new AssetReturn();
        value.setReturnNo(createReturnNo());
        value.setAssetId(asset.getId());
        value.setApplicationId(asset.getApplicationId());
        value.setAssetType(asset.getAssetType());
        value.setAssetName(asset.getAssetName());
        value.setAssetCode(asset.getAssetCode());
        value.setProjectId(asset.getProjectId());
        value.setProjectName(asset.getProjectName());
        value.setChannelId(asset.getChannelId());
        value.setChannelName(asset.getChannelName());
        value.setAssigneeId(asset.getAssigneeId());
        value.setAssigneeName(asset.getAssigneeName());
        value.setReason(reason);
        value.setStatus(STATUS_PENDING);
        value.setRequestedById(user.userId());
        value.setRequestedByName(user.displayName());
        return value;
    }

    private boolean canManage(CurrentUser user) {
        return user.authorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch(MANAGE_AUTHORITY::equals);
    }

    private String createReturnNo() {
        int suffix = ThreadLocalRandom.current().nextInt(100_000, 1_000_000);
        return "RTN" + LocalDateTime.now().format(RETURN_NO_TIME) + suffix;
    }

    private String normalizeOutcome(String outcome) {
        String value = outcome == null ? "" : outcome.trim().toUpperCase(Locale.ROOT);
        if (!OUTCOMES.contains(value)) {
            throw BusinessException.validation("回收结果仅支持重新入库或停用");
        }
        return value;
    }

    private String statusOrNull(String status) {
        String value = textOrNull(status);
        if (value == null) return null;
        value = value.toUpperCase(Locale.ROOT);
        if (!Set.of(STATUS_PENDING, STATUS_COMPLETED).contains(value)) {
            throw BusinessException.validation("回收状态仅支持待处理或已完成");
        }
        return value;
    }

    private String assetTypeOrNull(String assetType) {
        String value = textOrNull(assetType);
        if (value == null) return null;
        value = value.toUpperCase(Locale.ROOT);
        if (!ASSET_TYPES.contains(value)) {
            throw BusinessException.validation("不支持该资产类型筛选");
        }
        return value;
    }

    private String assetSubtypeOrNull(String assetType, String assetSubtype) {
        String value = textOrNull(assetSubtype);
        if (value == null) return null;
        value = value.toLowerCase(Locale.ROOT);
        if (!"PERSONAL".equals(assetType) || !PERSONAL_ASSET_SUBTYPES.contains(value)) {
            throw BusinessException.validation("不支持该资产子类型筛选");
        }
        return value;
    }

    private String textOrNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
