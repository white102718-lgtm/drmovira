package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Batch;
import com.adpulse.main.deliveryreport.google.DeliveryReportGooglePushModels.Item;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 在单一MySQL事务中固化推送批次及全部明细快照。 */
@Service
public class DeliveryReportGooglePushBatchStore {
    private final DeliveryReportGooglePushMapper mapper;

    public DeliveryReportGooglePushBatchStore(DeliveryReportGooglePushMapper mapper) {
        this.mapper = mapper;
    }

    /** 外部数据读取完成后再开启事务，避免Google或Doris调用占用数据库事务。 */
    @Transactional
    public Long create(Long requestedBy, List<Item> items) {
        Batch batch = new Batch();
        batch.setTotalCount(items.size());
        batch.setRequestedBy(requestedBy);
        mapper.insertBatch(batch);
        for (Item item : items) {
            item.setBatchId(batch.getId());
            mapper.insertItem(item);
        }
        return batch.getId();
    }
}
