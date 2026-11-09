package com.adpulse.main.task.mongo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

/** 验证真实 Mongo 字段映射、来源过滤、分页及故障语义。 */
class MongoMaterialTaskQueryProviderTest {
    private final MongoTemplate mongo = mock(MongoTemplate.class);
    private final MongoMaterialTaskQueryProvider provider =
            new MongoMaterialTaskQueryProvider(mongo);

    @Test
    void mapsMongoFieldsAndQueriesOnlyActiveLinkedOrders() {
        ObjectId id = new ObjectId();
        Instant createdAt = Instant.parse("2026-09-10T02:00:00Z");
        var row =
                new Document("_id", id)
                        .append("title", "素材任务")
                        .append("order_no", "MO-001")
                        .append("task_code", "MAT-001")
                        .append("status", "in_production")
                        .append("creator", "创建人")
                        .append("quantity", 5)
                        .append("completed_quantity", 2L)
                        .append("created_at", Date.from(createdAt));
        when(mongo.count(any(Query.class), eq("material_orders"))).thenReturn(21L);
        when(mongo.find(any(Query.class), eq(Document.class), eq("material_orders")))
                .thenReturn(List.of(row));
        var result = provider.findBySourceTaskId(7L, 2, 20);
        assertThat(result.total()).isEqualTo(21);
        var item = result.items().getFirst();
        assertThat(item.id()).isEqualTo(id.toHexString());
        assertThat(item.title()).isEqualTo("素材任务");
        assertThat(item.taskCode()).isEqualTo("MAT-001");
        assertThat(item.requesterName()).isEqualTo("创建人");
        assertThat(item.completedQuantity()).isEqualTo(2);
        assertThat(item.createdAt()).isEqualTo(createdAt);
        assertThat(item.expectedDeliveryAt()).isNull();
        var query = ArgumentCaptor.forClass(Query.class);
        verify(mongo).find(query.capture(), eq(Document.class), eq("material_orders"));
        assertThat(query.getValue().getQueryObject())
                .isEqualTo(
                        Document.parse(
                                "{ '$and': [ { 'source_task_id': { '$in': ['7', {'$numberLong': '7'}] } }, { '$or': [{ 'deleted_at': null }, { 'deleted_at': 0 }] } ] }"
                                        .replace('\'', '"')));
        assertThat(query.getValue().getSkip()).isEqualTo(20);
        assertThat(query.getValue().getLimit()).isEqualTo(20);
        assertThat(query.getValue().getSortObject())
                .isEqualTo(new Document("created_at", -1).append("_id", -1));
    }

    @Test
    void returnsEmptyWhenNoOrdersAreLinked() {
        when(mongo.find(any(Query.class), eq(Document.class), eq("material_orders")))
                .thenReturn(List.of());
        assertThat(provider.findBySourceTaskId(1L, 1, 20).items()).isEmpty();
    }

    @Test
    void doesNotTurnDatabaseFailureIntoEmptySuccess() {
        when(mongo.count(any(Query.class), eq("material_orders")))
                .thenThrow(new DataAccessResourceFailureException("unavailable"));
        assertThatThrownBy(() -> provider.findBySourceTaskId(1L, 1, 20))
                .isInstanceOf(DataAccessResourceFailureException.class);
    }
}
