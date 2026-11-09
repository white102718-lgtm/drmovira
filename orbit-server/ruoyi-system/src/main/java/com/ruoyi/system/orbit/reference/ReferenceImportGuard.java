package com.ruoyi.system.orbit.reference;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.Normalizer;
import java.util.*;
import org.springframework.stereotype.Component;

/** 最小引用目录导入合同：结构错误拒绝请求，逐行业务错误供预览展示；不代替数据库授权和引用复核。 */
@Component
public final class ReferenceImportGuard {
    public static final long MAX_REVISION = 9_007_199_254_740_991L;
    public static final int MAX_BODY_BYTES = 2 * 1024 * 1024;
    private static final Set<String> KINDS = Set.of("PRODUCT", "BUSINESS_AGENT", "VENDOR");
    private static final Set<String> ROOT_FIELDS =
            Set.of("kind", "source", "reason", "base_catalog_revision", "items");
    private static final Set<String> COMMON_FIELDS =
            Set.of(
                    "kind",
                    "id",
                    "name",
                    "availability",
                    "owner_team_id",
                    "data_owner_user_ids",
                    "source_key");
    private final ObjectMapper json;

    public ReferenceImportGuard(ObjectMapper json) {
        this.json = json.copy().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
    }

    /** row按合同从0开始；错误消息仅给字段位置，不回显原始名称、来源或拥有者。 */
    public record Issue(int row, String code, String message) {}

    public record Item(
            String kind,
            String id,
            String name,
            String availability,
            String teamId,
            List<String> ownerIds,
            String sourceKey,
            List<String> agentIds) {
        public Item {
            ownerIds = List.copyOf(ownerIds);
            agentIds = List.copyOf(agentIds);
        }

        @Override
        public String toString() {
            return "ReferenceItem[REDACTED]";
        }
    }

    /** body用于持久化及幂等指纹；不得作为日志打印；有issues的预览绝不允许进入提交。 */
    public record Prepared(
            String kind,
            String source,
            String reason,
            long baseRevision,
            List<Item> items,
            List<Issue> issues,
            String body,
            String hash) {
        public Prepared {
            items = List.copyOf(items);
            issues = List.copyOf(issues);
        }

        @Override
        public String toString() {
            return "ReferenceImport[REDACTED]";
        }
    }

    public static final class Failure extends RuntimeException {
        public final int status;
        public final String code, pointer;

        public Failure(int status, String code, String pointer) {
            super("引用目录字段无效：" + pointer);
            this.status = status;
            this.code = code;
            this.pointer = pointer;
        }
    }

    /** 从原始UTF-8字节执行硬上限；重复JSON键不得被解析器悄悄覆盖。 */
    public Prepared parse(byte[] utf8) {
        if (utf8 == null) throw structure("");
        if (utf8.length > MAX_BODY_BYTES) throw new Failure(413, "BODY_TOO_LARGE", "");
        try (var parser = json.getFactory().createParser(utf8)) {
            parser.enable(com.fasterxml.jackson.core.JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
            JsonNode node = json.readTree(parser);
            if (parser.nextToken() != null) throw structure("");
            return prepare(node);
        } catch (Failure failure) {
            throw failure;
        } catch (Exception failure) {
            throw structure("");
        }
    }

    public Prepared prepare(JsonNode input) {
        exact(input, ROOT_FIELDS, "");
        String kind = text(input.get("kind"), "/kind");
        if (!KINDS.contains(kind)) throw field("/kind");
        String source = normalized(text(input.get("source"), "/source"), 255, "/source");
        String reason = normalized(text(input.get("reason"), "/reason"), 1000, "/reason");
        JsonNode revision = input.get("base_catalog_revision");
        if (!revision.isIntegralNumber()) throw structure("/base_catalog_revision");
        if (!revision.canConvertToLong()
                || revision.longValue() < 0
                || revision.longValue() > MAX_REVISION) throw field("/base_catalog_revision");
        JsonNode entries = input.get("items");
        if (!entries.isArray()) throw structure("/items");
        if (entries.isEmpty() || entries.size() > 500) throw field("/items");
        ObjectNode canonical = input.deepCopy();
        canonical.put("source", source).put("reason", reason);
        List<Issue> issues = new ArrayList<>();
        List<Item> items = new ArrayList<>();
        Set<String> ids = new HashSet<>(), sources = new HashSet<>();
        for (int row = 0; row < entries.size(); row++) {
            JsonNode entry = entries.get(row);
            String pointer = "/items/" + row;
            String declaredKind = text(entry == null ? null : entry.get("kind"), pointer + "/kind");
            Set<String> fields = new HashSet<>(COMMON_FIELDS);
            if ("PRODUCT".equals(declaredKind)) fields.add("allowed_agent_ids");
            exact(entry, fields, pointer);
            // 类型错误属于整个JSON结构错误；不得先遇到某行非法UUID就漏掉后续结构错误。
            for (String f : COMMON_FIELDS)
                if (!"data_owner_user_ids".equals(f)) text(entry.get(f), pointer + "/" + f);
            arrayShape(entry.get("data_owner_user_ids"), pointer + "/data_owner_user_ids");
            if ("PRODUCT".equals(declaredKind))
                arrayShape(entry.get("allowed_agent_ids"), pointer + "/allowed_agent_ids");
            int first = issues.size();
            String itemKind = entry.get("kind").textValue();
            if (!kind.equals(itemKind) || !KINDS.contains(itemKind))
                issue(issues, row, "KIND_MISMATCH", pointer + "/kind");
            String id = rowUuid(entry.get("id").textValue(), row, pointer + "/id", issues);
            String name =
                    rowText(entry.get("name").textValue(), 255, row, pointer + "/name", issues);
            String availability = entry.get("availability").textValue();
            if (!Set.of("AVAILABLE", "UNAVAILABLE").contains(availability))
                issue(issues, row, "FIELD_VALIDATION_FAILED", pointer + "/availability");
            String team =
                    rowUuid(
                            entry.get("owner_team_id").textValue(),
                            row,
                            pointer + "/owner_team_id",
                            issues);
            String sourceKey =
                    rowText(
                            entry.get("source_key").textValue(),
                            128,
                            row,
                            pointer + "/source_key",
                            issues);
            List<String> owners =
                    uuidSet(
                            entry.get("data_owner_user_ids"),
                            row,
                            pointer + "/data_owner_user_ids",
                            issues);
            List<String> agents =
                    "PRODUCT".equals(declaredKind)
                            ? uuidSet(
                                    entry.get("allowed_agent_ids"),
                                    row,
                                    pointer + "/allowed_agent_ids",
                                    issues)
                            : List.of();
            if (id != null && !ids.add(id)) issue(issues, row, "DUPLICATE_ID", pointer + "/id");
            if (sourceKey != null && !sources.add(sourceKey))
                issue(issues, row, "DUPLICATE_SOURCE_KEY", pointer + "/source_key");
            if (first == issues.size()) {
                Item item = new Item(kind, id, name, availability, team, owners, sourceKey, agents);
                items.add(item);
                ObjectNode normalized = (ObjectNode) canonical.path("items").get(row);
                normalized
                        .put("id", id)
                        .put("name", name)
                        .put("owner_team_id", team)
                        .put("source_key", sourceKey);
                normalized.set("data_owner_user_ids", json.valueToTree(owners));
                if ("PRODUCT".equals(kind))
                    normalized.set("allowed_agent_ids", json.valueToTree(agents));
            }
        }
        try {
            String body = json.writeValueAsString(json.convertValue(canonical, Map.class));
            String hash =
                    HexFormat.of()
                            .formatHex(
                                    MessageDigest.getInstance("SHA-256")
                                            .digest(body.getBytes(StandardCharsets.UTF_8)));
            return new Prepared(
                    kind, source, reason, revision.longValue(), items, issues, body, hash);
        } catch (Exception error) {
            throw structure("");
        }
    }

    private static void exact(JsonNode node, Set<String> fields, String pointer) {
        if (node == null || !node.isObject()) throw structure(pointer);
        var names = node.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (!fields.contains(name))
                throw new Failure(
                        400,
                        "UNKNOWN_FIELD",
                        pointer + "/" + name.replace("~", "~0").replace("/", "~1"));
        }
        for (String f : new TreeSet<>(fields)) if (!node.has(f)) throw structure(pointer + "/" + f);
    }

    private static String text(JsonNode node, String pointer) {
        if (node == null || !node.isTextual()) throw structure(pointer);
        return node.textValue();
    }

    private static void arrayShape(JsonNode node, String pointer) {
        if (node == null || !node.isArray()) throw structure(pointer);
        for (int i = 0; i < node.size(); i++) text(node.get(i), pointer + "/" + i);
    }

    private static String normalized(String value, int maximum, String pointer) {
        if (value.codePoints()
                .anyMatch(
                        c ->
                                Character.isISOControl(c)
                                        || c == 0x2028
                                        || c == 0x2029
                                        || (c >= 0xd800 && c <= 0xdfff))) throw field(pointer);
        String n = Normalizer.normalize(value, Normalizer.Form.NFC).strip();
        if (n.isEmpty()
                || n.codePointCount(0, n.length()) > maximum
                || n.codePoints()
                        .anyMatch(c -> Character.isISOControl(c) || c == 0x2028 || c == 0x2029))
            throw field(pointer);
        return n;
    }

    private static String rowText(
            String value, int max, int row, String pointer, List<Issue> issues) {
        try {
            return normalized(value, max, pointer);
        } catch (Failure failure) {
            issue(issues, row, failure.code, pointer);
            return null;
        }
    }

    private static String rowUuid(String value, int row, String pointer, List<Issue> issues) {
        try {
            String id = UUID.fromString(value).toString();
            if (!id.equalsIgnoreCase(value)) throw new IllegalArgumentException();
            return id;
        } catch (IllegalArgumentException failure) {
            issue(issues, row, "INVALID_UUID", pointer);
            return null;
        }
    }

    private static List<String> uuidSet(
            JsonNode node, int row, String pointer, List<Issue> issues) {
        if (node.isEmpty() || node.size() > 500)
            issue(issues, row, "FIELD_VALIDATION_FAILED", pointer);
        Set<String> result = new TreeSet<>();
        for (int i = 0; i < node.size(); i++) {
            String id = rowUuid(node.get(i).textValue(), row, pointer + "/" + i, issues);
            if (id != null && !result.add(id))
                issue(issues, row, "DUPLICATE_REFERENCE", pointer + "/" + i);
        }
        return List.copyOf(result);
    }

    private static void issue(List<Issue> issues, int row, String code, String pointer) {
        issues.add(new Issue(row, code, "字段校验失败：" + pointer));
    }

    private static Failure structure(String pointer) {
        return new Failure(400, "INVALID_STRUCTURE", pointer);
    }

    private static Failure field(String pointer) {
        return new Failure(422, "FIELD_VALIDATION_FAILED", pointer);
    }
}
