package com.adpulse.main.manualtask;

import com.adpulse.main.adaccountasset.AdAccountAssetModels.AdAccountAssetAssignment;
import com.adpulse.main.manualtask.ManualTaskModels.AssignmentResult;
import com.adpulse.main.manualtask.ManualTaskModels.UserCandidate;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 在单账户事务中追加飞书使用人，绝不释放或覆盖既有使用人关系。 */
@Service
public class FeishuAdAccountAssignmentWriter {
    private final ManualTaskMapper mapper;

    public FeishuAdAccountAssignmentWriter(ManualTaskMapper mapper) {
        this.mapper = mapper;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AssignmentResult append(String accountId, List<UserCandidate> users, Long operatorId) {
        var asset = mapper.lockAssetByAccountId(accountId);
        if (asset == null) return new AssignmentResult(false, 0, 0);
        var assignments = mapper.findActiveAssignments(asset.getId());
        Set<Long> existingIds = new HashSet<>();
        assignments.forEach(a -> existingIds.add(a.getUserId()));
        int added = 0;
        int existing = 0;
        for (UserCandidate user : users) {
            if (existingIds.contains(user.getId())) {
                existing++;
                continue;
            }
            AdAccountAssetAssignment assignment = new AdAccountAssetAssignment();
            assignment.setAdAccountAssetId(asset.getId());
            assignment.setUserId(user.getId());
            assignment.setUserName(displayName(user));
            assignment.setIsPrimary(assignments.isEmpty() && added == 0);
            assignment.setCreatedBy(operatorId);
            assignment.setUpdatedBy(operatorId);
            int inserted = mapper.insertAssignment(assignment);
            if (inserted > 0) {
                added++;
                existingIds.add(user.getId());
            } else existing++;
        }
        if (added > 0) mapper.markAssetAssigned(asset.getId(), operatorId);
        return new AssignmentResult(true, added, existing);
    }

    private String displayName(UserCandidate user) {
        if (user.getRealName() != null && !user.getRealName().isBlank()) return user.getRealName();
        if (user.getDisplayName() != null && !user.getDisplayName().isBlank())
            return user.getDisplayName();
        return user.getUsername();
    }
}
