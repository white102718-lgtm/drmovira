package com.adpulse.system.feishuorg.service;

import com.adpulse.system.asset.service.AssetService;
import com.adpulse.system.auth.service.SessionStore;
import com.adpulse.system.common.util.PhoneNumberNormalizer;
import com.adpulse.system.department.mapper.DepartmentMapper;
import com.adpulse.system.department.model.Department;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncResult;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.DepartmentRecord;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.UserRecord;
import com.adpulse.system.user.model.UserAccount;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/** 将已校验的飞书快照原子写入系统组织主数据。 */
@Service
public class FeishuOrganizationSyncWriter {

    private final FeishuOrganizationMapper mapper;
    private final DepartmentMapper departmentMapper;
    private final PasswordEncoder passwordEncoder;
    private final SessionStore sessionStore;
    private final AssetService assetService;

    public FeishuOrganizationSyncWriter(
            FeishuOrganizationMapper mapper,
            DepartmentMapper departmentMapper,
            PasswordEncoder passwordEncoder,
            SessionStore sessionStore,
            AssetService assetService) {
        this.mapper = mapper;
        this.departmentMapper = departmentMapper;
        this.passwordEncoder = passwordEncoder;
        this.sessionStore = sessionStore;
        this.assetService = assetService;
    }

    /** 按部门、人员、缺失记录顺序写入一次完整同步。 */
    @Transactional
    public SyncResult synchronize(
            FeishuOrganizationSnapshot snapshot, Long operatorId, List<String> conflicts) {
        Map<String, Department> existingDepartments = indexDepartments(snapshot.tenantKey());
        Map<String, Long> departmentIds = new HashMap<>();
        existingDepartments.forEach(
                (externalId, department) -> departmentIds.put(externalId, department.getId()));

        int departmentCreated = 0;
        int departmentUpdated = 0;
        List<DepartmentRecord> pending = new ArrayList<>(snapshot.departments());
        while (!pending.isEmpty()) {
            int sizeBefore = pending.size();
            var iterator = pending.iterator();
            while (iterator.hasNext()) {
                DepartmentRecord record = iterator.next();
                Long parentId = resolveParentId(record.parentDepartmentId(), departmentIds);
                if (parentId == null) continue;
                Department parent = parentId == 0 ? null : departmentMapper.findById(parentId);
                Department department = existingDepartments.get(record.departmentId());
                boolean created = department == null;
                if (created) department = new Department();
                String oldPath = created ? null : department.getPath();
                int oldLevel = created ? 0 : department.getLevel();
                applyDepartment(department, record, snapshot.tenantKey(), parent, operatorId);
                if (created) {
                    mapper.insertDepartment(department);
                    department.setPath(
                            (parent == null ? "/" : parent.getPath()) + department.getId() + "/");
                    mapper.updateDepartment(department);
                    departmentCreated++;
                } else {
                    department.setPath(
                            (parent == null ? "/" : parent.getPath()) + department.getId() + "/");
                    mapper.updateDepartment(department);
                    if (!department.getPath().equals(oldPath)) {
                        departmentMapper.updateSubtreePath(
                                oldPath,
                                department.getPath(),
                                department.getLevel() - oldLevel,
                                operatorId);
                    }
                    departmentUpdated++;
                }
                existingDepartments.put(record.departmentId(), department);
                departmentIds.put(record.departmentId(), department.getId());
                iterator.remove();
            }
            if (pending.size() == sizeBefore) {
                pending.forEach(record -> conflicts.add("部门父级不存在：" + record.name()));
                break;
            }
        }

        Map<String, UserAccount> existingUsers = indexUsers(snapshot.tenantKey());
        int userCreated = 0;
        int userUpdated = 0;
        int explicitlyDisabled = 0;
        for (UserRecord record : snapshot.users()) {
            if (!StringUtils.hasText(record.userId())) {
                conflicts.add("存在缺少 user_id 的飞书人员：" + record.name());
                continue;
            }
            UserAccount user = existingUsers.get(record.userId());
            boolean created = user == null;
            if (created) {
                user = new UserAccount();
                user.setPasswordHash(passwordEncoder.encode(UUID.randomUUID().toString()));
                user.setCreatedBy(operatorId);
            }
            int oldStatus = created ? 0 : user.getStatus();
            applyUser(user, record, snapshot.tenantKey(), departmentIds, operatorId);
            if (created) {
                mapper.insertUser(user);
                userCreated++;
            } else {
                mapper.updateUser(user);
                userUpdated++;
                if (oldStatus == 1 && user.getStatus() == 0) {
                    assetService.releaseAssetsForDepartingUser(user.getId(), operatorId);
                    sessionStore.revokeUser(user.getId());
                    explicitlyDisabled++;
                }
            }
            existingUsers.put(record.userId(), user);
        }

        for (DepartmentRecord record : snapshot.departments()) {
            Department department = existingDepartments.get(record.departmentId());
            UserAccount leader = existingUsers.get(record.leaderUserId());
            if (department != null) {
                mapper.updateDepartmentLeader(
                        department.getId(), leader == null ? null : leader.getId(), operatorId);
            }
        }

        List<String> departmentExternalIds =
                snapshot.departments().stream().map(DepartmentRecord::departmentId).toList();
        int departmentDisabled =
                mapper.disableMissingDepartments(
                        snapshot.tenantKey(), departmentExternalIds, operatorId);
        List<String> userExternalIds = snapshot.users().stream().map(UserRecord::userId).toList();
        List<Long> disabledUserIds =
                mapper.findMissingActiveUserIds(snapshot.tenantKey(), userExternalIds);
        if (!disabledUserIds.isEmpty()) {
            disabledUserIds.forEach(
                    userId -> assetService.releaseAssetsForDepartingUser(userId, operatorId));
            mapper.disableUsers(disabledUserIds, operatorId);
            disabledUserIds.forEach(sessionStore::revokeUser);
        }
        return new SyncResult(
                snapshot.departments().size(),
                departmentCreated,
                departmentUpdated,
                departmentDisabled,
                snapshot.users().size(),
                userCreated,
                userUpdated,
                disabledUserIds.size() + explicitlyDisabled,
                conflicts.size(),
                List.copyOf(conflicts));
    }

    private Map<String, Department> indexDepartments(String tenantKey) {
        Map<String, Department> result = new LinkedHashMap<>();
        mapper.findDepartments(tenantKey).forEach(item -> result.put(item.getExternalId(), item));
        return result;
    }

    private Map<String, UserAccount> indexUsers(String tenantKey) {
        Map<String, UserAccount> result = new LinkedHashMap<>();
        mapper.findUsers(tenantKey).forEach(item -> result.put(item.getExternalId(), item));
        return result;
    }

    private Long resolveParentId(String externalParentId, Map<String, Long> departmentIds) {
        if (!StringUtils.hasText(externalParentId) || "0".equals(externalParentId)) return 0L;
        return departmentIds.get(externalParentId);
    }

    private void applyDepartment(
            Department department,
            DepartmentRecord record,
            String tenantKey,
            Department parent,
            Long operatorId) {
        department.setParentId(parent == null ? 0L : parent.getId());
        department.setDeptCode(
                "FS_"
                        + UUID.nameUUIDFromBytes(
                                        (tenantKey + ":" + record.departmentId())
                                                .getBytes(StandardCharsets.UTF_8))
                                .toString());
        department.setDeptName(record.name());
        department.setLevel(parent == null ? 1 : parent.getLevel() + 1);
        department.setSortOrder(record.order());
        department.setStatus(1);
        department.setSourceType("FEISHU");
        department.setTenantKey(tenantKey);
        department.setExternalId(record.departmentId());
        department.setUpdatedBy(operatorId);
        if (department.getCreatedBy() == null) department.setCreatedBy(operatorId);
    }

    private void applyUser(
            UserAccount user,
            UserRecord record,
            String tenantKey,
            Map<String, Long> departmentIds,
            Long operatorId) {
        user.setPhone(PhoneNumberNormalizer.normalize(record.mobile()));
        user.setDisplayName(record.name());
        user.setRealName(record.name());
        user.setPrimaryDepartmentId(
                record.departmentIds().stream()
                        .map(departmentIds::get)
                        .filter(java.util.Objects::nonNull)
                        .findFirst()
                        .orElse(null));
        user.setEmail(record.email());
        user.setAvatarUrl(record.avatarUrl());
        user.setStatus(record.active() ? 1 : 0);
        user.setSourceType("FEISHU");
        user.setTenantKey(tenantKey);
        user.setExternalId(record.userId());
        user.setFeishuOpenId(record.openId());
        user.setFeishuUnionId(record.unionId());
        user.setUpdatedBy(operatorId);
    }
}
