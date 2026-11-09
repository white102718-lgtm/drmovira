package com.adpulse.system.feishuorg.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.department.model.Department;
import com.adpulse.system.feishuorg.dto.FeishuOrganizationViews.SyncResult;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSchedule;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.DepartmentRecord;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.UserRecord;
import com.adpulse.system.user.model.UserAccount;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import org.springframework.stereotype.Service;

/** 在写入前校验组织完整性、缺失停用规模与人工确认的快照一致性。 */
@Service
public class FeishuOrganizationSafety {
    private final FeishuOrganizationMapper mapper;
    private final ObjectMapper json;

    public FeishuOrganizationSafety(FeishuOrganizationMapper mapper, ObjectMapper json) {
        this.mapper = mapper;
        this.json = json;
    }

    /** 读取当前应用的不可逆配置摘要，配置变更会使旧预览失效。 */
    public String appHash() {
        var config = mapper.findApplicationConfig();
        if (config == null || blank(config.getAppId()) || blank(config.getAppSecretCiphertext())) {
            throw BusinessException.conflict("请先配置飞书应用");
        }
        return digest(List.of(config.getAppId(), config.getAppSecretCiphertext()));
    }

    /** 差异统计只把启用记录计入停用，明确停用的人员与范围缺失分别判断。 */
    public Assessment assess(
            FeishuOrganizationSnapshot snapshot, FeishuOrganizationSchedule schedule) {
        List<Department> departments = mapper.findDepartments(snapshot.tenantKey());
        List<UserAccount> users = mapper.findUsers(snapshot.tenantKey());
        Map<String, DepartmentRecord> remoteDepartments = new HashMap<>();
        Map<String, UserRecord> remoteUsers = new HashMap<>();
        List<String> conflicts = new ArrayList<>();
        if (blank(snapshot.tenantKey())) conflicts.add("飞书租户标识缺失");
        for (var department : snapshot.departments()) {
            if (blank(department.departmentId()) || blank(department.name()))
                conflicts.add("飞书部门缺少标识或名称");
            if (remoteDepartments.put(department.departmentId(), department) != null)
                conflicts.add("飞书部门标识重复");
        }
        for (var department : snapshot.departments()) {
            Set<String> visited = new HashSet<>();
            var current = department;
            while (current != null
                    && !blank(current.parentDepartmentId())
                    && !"0".equals(current.parentDepartmentId())) {
                if (!visited.add(current.departmentId())) {
                    conflicts.add("部门层级存在循环");
                    break;
                }
                current = remoteDepartments.get(current.parentDepartmentId());
                if (current == null) conflicts.add("部门父级不在同步范围");
            }
        }
        for (var user : snapshot.users()) {
            if (blank(user.userId()) || blank(user.name())) conflicts.add("飞书人员缺少标识或姓名");
            if (remoteUsers.put(user.userId(), user) != null) conflicts.add("飞书人员标识重复");
            if (user.departmentIds() == null
                    || user.departmentIds().isEmpty()
                    || user.departmentIds().stream()
                            .anyMatch(id -> !remoteDepartments.containsKey(id))) {
                conflicts.add("人员所属部门不在同步范围");
            }
        }
        if (snapshot.departments().isEmpty() && !departments.isEmpty())
            conflicts.add("空部门快照，禁止批量停用");
        if (snapshot.users().isEmpty() && !users.isEmpty()) conflicts.add("空人员快照，禁止批量停用");
        int departmentMissing =
                (int)
                        departments.stream()
                                .filter(
                                        d ->
                                                d.getStatus() == 1
                                                        && !remoteDepartments.containsKey(
                                                                d.getExternalId()))
                                .count();
        int userMissing =
                (int)
                        users.stream()
                                .filter(
                                        u ->
                                                u.getStatus() == 1
                                                        && !remoteUsers.containsKey(
                                                                u.getExternalId()))
                                .count();
        int explicitlyDisabled =
                (int)
                        users.stream()
                                .filter(
                                        u ->
                                                u.getStatus() == 1
                                                        && remoteUsers.containsKey(
                                                                u.getExternalId())
                                                        && !remoteUsers
                                                                .get(u.getExternalId())
                                                                .active())
                                .count();
        Set<String> departmentIds = new HashSet<>();
        departments.forEach(d -> departmentIds.add(d.getExternalId()));
        Set<String> userIds = new HashSet<>();
        users.forEach(u -> userIds.add(u.getExternalId()));
        int departmentCreated =
                (int)
                        remoteDepartments.keySet().stream()
                                .filter(id -> !departmentIds.contains(id))
                                .count();
        int userCreated =
                (int) remoteUsers.keySet().stream().filter(id -> !userIds.contains(id)).count();
        SyncResult result =
                new SyncResult(
                        snapshot.departments().size(),
                        departmentCreated,
                        snapshot.departments().size() - departmentCreated,
                        departmentMissing,
                        snapshot.users().size(),
                        userCreated,
                        snapshot.users().size() - userCreated,
                        userMissing + explicitlyDisabled,
                        conflicts.size(),
                        List.copyOf(conflicts));
        boolean requiresReview =
                exceeds(
                                departmentMissing,
                                departments.stream().filter(d -> d.getStatus() == 1).count(),
                                schedule)
                        || exceeds(
                                userMissing,
                                users.stream().filter(u -> u.getStatus() == 1).count(),
                                schedule);
        // 同时绑定本地启停基线，另一轮同步完成后不能复用之前的人工确认。
        String hash =
                digest(
                        Arrays.asList(
                                snapshot.tenantKey(),
                                snapshot.departments().stream()
                                        .sorted(
                                                Comparator.comparing(
                                                        DepartmentRecord::departmentId,
                                                        Comparator.nullsFirst(
                                                                Comparator.naturalOrder())))
                                        .toList(),
                                snapshot.users().stream()
                                        .sorted(
                                                Comparator.comparing(
                                                        UserRecord::userId,
                                                        Comparator.nullsFirst(
                                                                Comparator.naturalOrder())))
                                        .toList(),
                                departments.stream()
                                        .map(
                                                d ->
                                                        Arrays.asList(
                                                                d.getId(),
                                                                d.getExternalId(),
                                                                d.getStatus()))
                                        .toList(),
                                users.stream()
                                        .map(
                                                u ->
                                                        Arrays.asList(
                                                                u.getId(),
                                                                u.getExternalId(),
                                                                u.getStatus()))
                                        .toList()));
        return new Assessment(result, requiresReview, hash);
    }

    private boolean exceeds(int missing, long active, FeishuOrganizationSchedule schedule) {
        return missing > 0
                && (missing >= schedule.getMissingCountLimit()
                        || missing * 100L >= active * schedule.getMissingPercentLimit());
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private String digest(Object value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(
                                            json.writeValueAsString(value)
                                                    .getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException | JsonProcessingException exception) {
            throw new IllegalStateException("无法生成组织同步校验摘要", exception);
        }
    }

    /** 本次差异、缺失保护判断及可用于确认的摘要。 */
    public record Assessment(SyncResult result, boolean requiresReview, String hash) {}
}
