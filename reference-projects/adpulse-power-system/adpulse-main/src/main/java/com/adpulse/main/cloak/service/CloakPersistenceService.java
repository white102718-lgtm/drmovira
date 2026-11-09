package com.adpulse.main.cloak.service;

import com.adpulse.main.cloak.mapper.CloakMapper;
import com.adpulse.main.cloak.model.CloakBatch;
import com.adpulse.main.cloak.model.CloakRecord;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 斗篷批次的短事务持久化边界，避免远程HTTP调用占用数据库事务。 */
@Service
public class CloakPersistenceService {
    private static final int BATCH_PROCESSING = 1;
    private static final int BATCH_SUCCESS = 2;
    private static final int BATCH_FAILED = 3;
    private static final int BATCH_UNCERTAIN = 4;
    private static final int RECORD_PENDING = 0;
    private static final int RECORD_SUCCESS = 1;
    private static final int RECORD_FAILED = 2;
    private final CloakMapper mapper;

    public CloakPersistenceService(CloakMapper mapper) {
        this.mapper = mapper;
    }

    /** 创建幂等批次，或按相同载荷复用既有成功/失败批次。 */
    @Transactional
    public PrepareResult prepare(
            CloakBatch candidate, List<CloakRecord> records, Long requestedBy) {
        CloakBatch existing = mapper.findBatchByRequestId(candidate.getRequestId());
        if (existing != null) {
            if (!existing.getRequestFingerprint().equals(candidate.getRequestFingerprint())) {
                throw new CloakService.CloakException("同一requestId不能提交不同的斗篷数据");
            }
            if (existing.getStatus() == BATCH_SUCCESS) {
                return new PrepareResult(existing, false, true, false);
            }
            if (existing.getStatus() == BATCH_UNCERTAIN) {
                return new PrepareResult(existing, false, false, true);
            }
            if (existing.getStatus() != BATCH_FAILED) {
                throw new CloakService.CloakException("该批次正在处理，请勿重复提交");
            }
            resetForRetry(existing.getId(), requestedBy);
            existing.setStatus(BATCH_PROCESSING);
            return new PrepareResult(existing, true, false, false);
        }

        candidate.setStatus(BATCH_PROCESSING);
        candidate.setRequestedBy(requestedBy);
        mapper.insertBatch(candidate);
        for (CloakRecord record : records) {
            record.setBatchId(candidate.getId());
            record.setStatus(RECORD_PENDING);
            record.setCreatedBy(requestedBy);
            record.setUpdatedBy(requestedBy);
            mapper.insertRecord(record);
        }
        return new PrepareResult(candidate, true, false, false);
    }

    /** 远端对账确认不存在后，将明确失败或待核对批次恢复为可重试状态。 */
    @Transactional
    public void resetForRetry(Long batchId, Long operatorId) {
        if (mapper.resetBatch(batchId, operatorId) != 1) {
            throw new CloakService.CloakException("批次状态已变化，请刷新后重试");
        }
        mapper.resetRecords(batchId, operatorId);
    }

    /** 将服务商整批成功结果原子写入批次和全部明细。 */
    @Transactional
    public void markSuccess(Long batchId, int totalCount, String providerMessage, Long operatorId) {
        mapper.markBatchSuccess(batchId, totalCount, safeMessage(providerMessage));
        mapper.updateRecordStatus(batchId, RECORD_SUCCESS, operatorId);
        mapper.updateAgencyLineCloakUrlsByBatch(batchId, operatorId);
    }

    /** 幂等请求复用既有成功批次时，再次确保推广链接已经回填代理线。 */
    @Transactional
    public void backfillAgencyLineCloakUrls(Long batchId, Long operatorId) {
        mapper.updateAgencyLineCloakUrlsByBatch(batchId, operatorId);
    }

    /** 保存明确失败或结果不确定状态，列表不会展示这些明细。 */
    @Transactional
    public void markFailed(Long batchId, boolean uncertain, String errorMessage, Long operatorId) {
        mapper.markBatchFailed(batchId, uncertain ? 4 : BATCH_FAILED, safeMessage(errorMessage));
        mapper.updateRecordStatus(batchId, uncertain ? 3 : RECORD_FAILED, operatorId);
    }

    /** 服务商删除成功后，将对应本地记录一次性软删除。 */
    @Transactional
    public void softDeleteRecords(List<Long> ids, Long operatorId) {
        int affected = mapper.softDeleteRecords(ids, System.currentTimeMillis(), operatorId);
        if (affected != ids.size()) {
            throw new CloakService.CloakException("斗篷记录状态已变化，请刷新后重试");
        }
    }

    /** 独立保存一条表格回写结果，避免同批其他记录失败时回滚。 */
    @Transactional
    public void markSheetWriteback(
            Long recordId,
            boolean success,
            String message,
            Integer rowNumber,
            Long operatorId) {
        int affected =
                mapper.updateSheetWriteback(
                        recordId,
                        success ? 1 : 2,
                        safeMessage(message),
                        rowNumber,
                        operatorId);
        if (affected != 1) {
            throw new CloakService.CloakException("斗篷记录状态已变化，请刷新后重试");
        }
    }

    private String safeMessage(String value) {
        if (value == null) return null;
        return value.length() <= 1000 ? value : value.substring(0, 1000);
    }

    /** 幂等准备结果。 */
    public record PrepareResult(
            CloakBatch batch,
            boolean shouldCallProvider,
            boolean reused,
            boolean shouldReconcileProvider) {}
}
