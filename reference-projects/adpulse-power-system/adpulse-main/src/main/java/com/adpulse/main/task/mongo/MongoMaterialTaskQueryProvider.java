package com.adpulse.main.task.mongo;

import com.adpulse.main.task.dto.TaskViews;
import java.time.Instant;
import java.util.Date;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

/** 按来源投放任务读取素材工单，MongoDB 只承担素材任务查询。 */
@Component
public class MongoMaterialTaskQueryProvider {
    private static final String COLLECTION = "material_orders";
    private final MongoTemplate mongoTemplate;

    public MongoMaterialTaskQueryProvider(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    /** 精确匹配来源任务 ID；兼容历史工单未设置软删除字段的情况。 */
    public TaskViews.Page<TaskViews.RelatedMaterialTask> findBySourceTaskId(
            Long taskId, int page, int pageSize) {
        Criteria criteria =
                new Criteria()
                        .andOperator(
                                Criteria.where("source_task_id").in(taskId.toString(), taskId),
                                new Criteria()
                                        .orOperator(
                                                Criteria.where("deleted_at").is(null),
                                                Criteria.where("deleted_at").is(0)));
        long total = mongoTemplate.count(new Query(criteria), COLLECTION);
        Query query =
                new Query(criteria)
                        .with(Sort.by(Sort.Direction.DESC, "created_at", "_id"))
                        .skip((long) (page - 1) * pageSize)
                        .limit(pageSize);
        query.fields()
                .include(
                        "_id",
                        "task_code",
                        "order_no",
                        "title",
                        "status",
                        "owner_name",
                        "requester_name",
                        "creator",
                        "quantity",
                        "completed_quantity",
                        "created_at",
                        "expected_delivery_at");
        var items =
                mongoTemplate.find(query, Document.class, COLLECTION).stream()
                        .map(this::toView)
                        .toList();
        return new TaskViews.Page<>(items, total, page, pageSize);
    }

    private TaskViews.RelatedMaterialTask toView(Document row) {
        return new TaskViews.RelatedMaterialTask(
                text(row, "_id"),
                text(row, "task_code"),
                text(row, "order_no"),
                text(row, "title"),
                text(row, "status"),
                text(row, "owner_name"),
                text(row, "requester_name") == null
                        ? text(row, "creator")
                        : text(row, "requester_name"),
                integer(row, "quantity"),
                integer(row, "completed_quantity"),
                instant(row, "created_at"),
                instant(row, "expected_delivery_at"));
    }

    private String text(Document row, String field) {
        Object value = row.get(field);
        return value == null ? null : value.toString();
    }

    private Integer integer(Document row, String field) {
        return row.get(field) instanceof Number value ? value.intValue() : null;
    }

    private Instant instant(Document row, String field) {
        return row.get(field) instanceof Date value ? value.toInstant() : null;
    }
}
