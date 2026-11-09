package com.adpulse.main.manualtask;

import com.adpulse.main.manualtask.ManualTaskModels.UserCandidate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

/** 全量扫描飞书账户使用记录，并将可唯一匹配的系统用户追加到广告账户。 */
@Component
public class FeishuAdAccountUserSyncTask implements ManualTaskDefinition {
    public static final String CODE = "SYNC_FEISHU_AD_ACCOUNT_USERS";
    private static final String COLLECTION = "feishu_account_used_record";
    private static final String NAME_SPLIT = "[,，/、;；\\r\\n]+";
    private final MongoTemplate mongoTemplate;
    private final ManualTaskMapper mapper;
    private final FeishuAdAccountAssignmentWriter writer;

    public FeishuAdAccountUserSyncTask(
            MongoTemplate mongoTemplate,
            ManualTaskMapper mapper,
            FeishuAdAccountAssignmentWriter writer) {
        this.mongoTemplate = mongoTemplate;
        this.mapper = mapper;
        this.writer = writer;
    }

    @Override
    public String code() {
        return CODE;
    }

    @Override
    public String name() {
        return "同步飞书广告账户使用人";
    }

    @Override
    public String description() {
        return "全量扫描飞书使用记录，只追加匹配到的广告账户使用人，不移除既有关系。";
    }

    @Override
    public void execute(ManualTaskContext context) {
        Query query = new Query();
        query.fields().include("account_id").include("user_name");
        List<Document> documents = mongoTemplate.find(query, Document.class, COLLECTION);
        context.log().info("MongoDB 全量扫描完成，共 " + documents.size() + " 条记录（不按 in_use 过滤）");
        Map<String, LinkedHashSet<String>> accountNames = merge(documents, context.log());
        Set<String> allNames = new LinkedHashSet<>();
        accountNames.values().forEach(allNames::addAll);
        List<UserCandidate> candidates = findCandidates(allNames);
        Map<String, List<UserCandidate>> realNames = index(candidates, true);
        Map<String, List<UserCandidate>> displayNames = index(candidates, false);

        int added = 0, existing = 0, missingAsset = 0, missingUser = 0, ambiguous = 0, failed = 0;
        for (var entry : accountNames.entrySet()) {
            List<UserCandidate> users = new ArrayList<>();
            Set<Long> ids = new LinkedHashSet<>();
            for (String name : entry.getValue()) {
                List<UserCandidate> matches = realNames.getOrDefault(name, List.of());
                if (matches.isEmpty()) matches = displayNames.getOrDefault(name, List.of());
                List<UserCandidate> distinctMatches =
                        matches.stream()
                                .collect(
                                        java.util.stream.Collectors.toMap(
                                                UserCandidate::getId,
                                                user -> user,
                                                (left, right) -> left))
                                .values()
                                .stream()
                                .toList();
                if (distinctMatches.isEmpty()) {
                    missingUser++;
                    context.log().warn("未匹配到有效系统用户：" + name + "，账户：" + entry.getKey());
                } else if (distinctMatches.size() > 1) {
                    ambiguous++;
                    context.log().warn("系统用户名称匹配不唯一：" + name + "，账户：" + entry.getKey());
                } else if (ids.add(distinctMatches.get(0).getId()))
                    users.add(distinctMatches.get(0));
            }
            if (users.isEmpty()) continue;
            try {
                var result = writer.append(entry.getKey(), users, context.operatorId());
                if (!result.assetFound()) {
                    missingAsset++;
                    context.log().warn("资产台账不存在账户：" + entry.getKey());
                    continue;
                }
                added += result.added();
                existing += result.existing();
                context.log()
                        .info(
                                "账户 "
                                        + entry.getKey()
                                        + "：新增 "
                                        + result.added()
                                        + " 人，已存在 "
                                        + result.existing()
                                        + " 人");
            } catch (RuntimeException exception) {
                failed++;
                context.log().error("账户 " + entry.getKey() + " 写入失败：" + exception.getMessage());
            }
        }
        context.log()
                .info(
                        "汇总：账户 "
                                + accountNames.size()
                                + "，新增关系 "
                                + added
                                + "，已存在 "
                                + existing
                                + "，缺失账户 "
                                + missingAsset
                                + "，未匹配用户 "
                                + missingUser
                                + "，歧义用户 "
                                + ambiguous
                                + "，失败账户 "
                                + failed);
        if (failed > 0) throw new IllegalStateException("有 " + failed + " 个账户写入失败，详情见日志");
    }

    private Map<String, LinkedHashSet<String>> merge(List<Document> documents, ManualTaskLog log) {
        Map<String, LinkedHashSet<String>> result = new LinkedHashMap<>();
        for (Document document : documents) {
            String accountId = normalizeAccountId(document.getString("account_id"));
            if (accountId == null) {
                log.warn("跳过缺少 account_id 的 MongoDB 记录");
                continue;
            }
            LinkedHashSet<String> names =
                    result.computeIfAbsent(accountId, ignored -> new LinkedHashSet<>());
            String raw = document.getString("user_name");
            if (raw == null || raw.isBlank()) {
                log.warn("账户 " + accountId + " 的 user_name 为空");
                continue;
            }
            for (String name : raw.split(NAME_SPLIT)) if (!name.isBlank()) names.add(name.trim());
        }
        return result;
    }

    private String normalizeAccountId(String value) {
        if (value == null || value.isBlank()) return null;
        String id = value.trim();
        return id.startsWith("act_") ? id.substring(4) : id;
    }

    private List<UserCandidate> findCandidates(Collection<String> names) {
        List<String> list = new ArrayList<>(names);
        List<UserCandidate> result = new ArrayList<>();
        if (list.isEmpty()) return result;
        for (int from = 0; from < list.size(); from += 500)
            result.addAll(
                    mapper.findUsersByNames(list.subList(from, Math.min(from + 500, list.size()))));
        return result;
    }

    private Map<String, List<UserCandidate>> index(List<UserCandidate> users, boolean realName) {
        Map<String, List<UserCandidate>> result = new LinkedHashMap<>();
        for (UserCandidate user : users) {
            String key = realName ? user.getRealName() : user.getDisplayName();
            if (key != null && !key.isBlank())
                result.computeIfAbsent(key.trim(), ignored -> new ArrayList<>()).add(user);
        }
        return result;
    }
}
