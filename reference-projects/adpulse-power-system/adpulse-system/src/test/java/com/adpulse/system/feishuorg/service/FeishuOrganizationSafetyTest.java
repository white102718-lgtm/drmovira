package com.adpulse.system.feishuorg.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import com.adpulse.system.department.model.Department;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSchedule;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.DepartmentRecord;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.UserRecord;
import com.adpulse.system.user.model.UserAccount;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** 缺失保护、启停统计、组织完整性及人工确认快照边界测试。 */
class FeishuOrganizationSafetyTest {
    private final FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
    private final FeishuOrganizationSafety safety =
            new FeishuOrganizationSafety(mapper, new ObjectMapper());
    private final DepartmentRecord root = new DepartmentRecord("root", "0", "公司", 0, null);

    @Test
    void distinguishesMissingUsersFromExplicitlyDisabledAndAlreadyInactiveUsers() {
        when(mapper.findUsers("tenant"))
                .thenReturn(List.of(localUser(1, 1), localUser(2, 1), localUser(3, 0)));
        var result = safety.assess(snapshot(List.of(remoteUser(1, false))), schedule(10, 60));
        assertThat(result.result().userDisabled()).isEqualTo(2);
        assertThat(result.requiresReview()).isFalse(); // 仅范围缺失的1人 / 原启用2人 = 50%
    }

    @Test
    void blocksAtPercentageBoundaryEvenWhenCountIsLow() {
        when(mapper.findUsers("tenant"))
                .thenReturn(IntStream.rangeClosed(1, 5).mapToObj(id -> localUser(id, 1)).toList());
        var result =
                safety.assess(
                        snapshot(
                                IntStream.rangeClosed(1, 4)
                                        .mapToObj(id -> remoteUser(id, true))
                                        .toList()),
                        schedule(10, 20));
        assertThat(result.requiresReview()).isTrue();
        assertThat(result.result().userDisabled()).isEqualTo(1);
    }

    @Test
    void blocksAtCountBoundaryEvenWhenPercentageIsLow() {
        when(mapper.findUsers("tenant"))
                .thenReturn(
                        IntStream.rangeClosed(1, 100).mapToObj(id -> localUser(id, 1)).toList());
        var result =
                safety.assess(
                        snapshot(
                                IntStream.rangeClosed(1, 90)
                                        .mapToObj(id -> remoteUser(id, true))
                                        .toList()),
                        schedule(10, 20));
        assertThat(result.requiresReview()).isTrue();
    }

    @Test
    void blocksMissingDepartmentsIndependentlyOfUsers() {
        var department = new Department();
        department.setId(1L);
        department.setExternalId("missing");
        department.setStatus(1);
        when(mapper.findDepartments("tenant")).thenReturn(List.of(department));
        assertThat(
                        safety.assess(snapshot(List.of(remoteUser(1, true))), schedule(10, 20))
                                .requiresReview())
                .isTrue();
    }

    @Test
    void rejectsEmptyUsersCyclesAndOutOfScopeMembership() {
        when(mapper.findUsers("tenant")).thenReturn(List.of(localUser(1, 1)));
        assertThat(safety.assess(snapshot(List.of()), schedule(10, 20)).result().conflicts())
                .contains("空人员快照，禁止批量停用");
        var cyclic =
                new FeishuOrganizationSnapshot(
                        "tenant",
                        List.of(
                                new DepartmentRecord("a", "b", "A", 0, null),
                                new DepartmentRecord("b", "a", "B", 0, null)),
                        List.of(remoteUser(1, true)));
        assertThat(safety.assess(cyclic, schedule(10, 20)).result().conflicts())
                .contains("部门层级存在循环", "人员所属部门不在同步范围");
    }

    @Test
    void acceptsFirstSyncAndChangesConfirmationHashWhenLocalStatusChanges() {
        var snapshot = snapshot(List.of(remoteUser(1, true)));
        assertThat(safety.assess(snapshot, schedule(10, 20)).requiresReview()).isFalse();
        when(mapper.findUsers("tenant")).thenReturn(List.of(localUser(1, 1)));
        String original = safety.assess(snapshot, schedule(10, 20)).hash();
        when(mapper.findUsers("tenant")).thenReturn(List.of(localUser(1, 0)));
        assertThat(safety.assess(snapshot, schedule(10, 20)).hash()).isNotEqualTo(original);
    }

    private FeishuOrganizationSnapshot snapshot(List<UserRecord> users) {
        return new FeishuOrganizationSnapshot("tenant", List.of(root), users);
    }

    private UserRecord remoteUser(int id, boolean active) {
        return new UserRecord(
                "u" + id, null, null, "用户" + id, null, null, null, active, List.of("root"));
    }

    private UserAccount localUser(int id, int status) {
        var user = new UserAccount();
        user.setId((long) id);
        user.setExternalId("u" + id);
        user.setStatus(status);
        return user;
    }

    private FeishuOrganizationSchedule schedule(int count, int percent) {
        var schedule = new FeishuOrganizationSchedule();
        schedule.setMissingCountLimit(count);
        schedule.setMissingPercentLimit(percent);
        return schedule;
    }
}
