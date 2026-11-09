package com.ruoyi.system.orbit.reference;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.junit.jupiter.api.Test;

/** 导入预览结构和逐行错误边界；不把格式测试冒充数据库引用或授权验收。 */
class ReferenceImportGuardTest {
    private final ObjectMapper json = new ObjectMapper();
    private final ReferenceImportGuard guard = new ReferenceImportGuard(json);
    private static final String ID = "abcdef00-0000-0000-0000-000000000001";
    private static final String TEAM = "abcdef00-0000-0000-0000-000000000002";
    private static final String OWNER = "abcdef00-0000-0000-0000-000000000003";
    private static final String AGENT = "abcdef00-0000-0000-0000-000000000004";

    private ObjectNode body(String kind) {
        ObjectNode root =
                json.createObjectNode()
                        .put("kind", kind)
                        .put("source", "迁移资料")
                        .put("reason", "保留原始引用")
                        .put("base_catalog_revision", 0);
        ObjectNode item =
                root.putArray("items")
                        .addObject()
                        .put("kind", kind)
                        .put("id", ID)
                        .put("name", "资料名称")
                        .put("availability", "AVAILABLE")
                        .put("owner_team_id", TEAM)
                        .put("source_key", "source-1");
        item.putArray("data_owner_user_ids").add(OWNER);
        if (kind.equals("PRODUCT")) item.putArray("allowed_agent_ids").add(AGENT);
        return root;
    }

    private ObjectNode item(ObjectNode root) {
        return (ObjectNode) root.path("items").get(0);
    }

    private void failure(ObjectNode root, int status, String code) {
        var f = assertThrows(ReferenceImportGuard.Failure.class, () -> guard.prepare(root));
        assertEquals(status, f.status);
        assertEquals(code, f.code);
    }

    @Test
    void threeKindsKeepOriginalIdsAndProductOnlyAgentSet() {
        for (String kind : List.of("PRODUCT", "BUSINESS_AGENT", "VENDOR")) {
            var result = guard.prepare(body(kind));
            assertTrue(result.issues().isEmpty());
            assertEquals(ID, result.items().get(0).id());
            assertEquals(
                    kind.equals("PRODUCT") ? List.of(AGENT) : List.of(),
                    result.items().get(0).agentIds());
            assertEquals(0, result.baseRevision());
            assertEquals(64, result.hash().length());
            assertFalse(result.toString().contains(ID));
            assertFalse(result.items().get(0).toString().contains(OWNER));
            assertThrows(UnsupportedOperationException.class, () -> result.items().clear());
            assertThrows(
                    UnsupportedOperationException.class,
                    () -> result.items().get(0).ownerIds().clear());
        }
    }

    @Test
    void requiredUnknownNullAndTypesAreWholeRequestErrors() {
        for (String f : List.of("kind", "source", "reason", "base_catalog_revision", "items")) {
            var b = body("VENDOR");
            b.remove(f);
            failure(b, 400, "INVALID_STRUCTURE");
            b = body("VENDOR");
            b.putNull(f);
            failure(b, 400, "INVALID_STRUCTURE");
        }
        for (String f :
                List.of(
                        "kind",
                        "id",
                        "name",
                        "availability",
                        "owner_team_id",
                        "source_key",
                        "data_owner_user_ids")) {
            var b = body("VENDOR");
            item(b).remove(f);
            failure(b, 400, "INVALID_STRUCTURE");
        }
        for (String f : List.of("tenant_id", "actor_id", "state", "revision")) {
            var b = body("VENDOR").put(f, "forged");
            failure(b, 400, "UNKNOWN_FIELD");
            b = body("VENDOR");
            item(b).put(f, "forged");
            failure(b, 400, "UNKNOWN_FIELD");
        }
        var product = body("PRODUCT");
        item(product).remove("allowed_agent_ids");
        failure(product, 400, "INVALID_STRUCTURE");
        var vendor = body("VENDOR");
        item(vendor).putArray("allowed_agent_ids").add(AGENT);
        failure(vendor, 400, "UNKNOWN_FIELD");
        var typed = body("VENDOR");
        item(typed).put("name", 1);
        failure(typed, 400, "INVALID_STRUCTURE");
        typed = body("VENDOR");
        item(typed).putArray("data_owner_user_ids").addNull();
        failure(typed, 400, "INVALID_STRUCTURE");
    }

    @Test
    void semanticRowErrorsAccumulateButLaterStructureStillFails() {
        var b = body("PRODUCT");
        item(b).put("id", "1-1-1-1-1")
                .put("name", " ")
                .put("availability", "ENABLED")
                .put("owner_team_id", "wrong")
                .put("source_key", "bad\nsource");
        item(b).putArray("data_owner_user_ids");
        item(b).putArray("allowed_agent_ids").add("wrong");
        var result = guard.prepare(b);
        assertEquals(7, result.issues().size());
        assertTrue(result.items().isEmpty());
        assertTrue(
                result.issues().stream()
                        .allMatch(i -> i.row() == 0 && !i.message().contains("wrong")));
        ObjectNode next = body("PRODUCT").withArray("items").get(0).deepCopy();
        next.put("id", 123);
        b.withArray("items").add(next);
        failure(b, 400, "INVALID_STRUCTURE");
    }

    @Test
    void mixedKindsAreRejectedRowsAndRawShortTextControlsCannotDisappearByTrim() {
        var b = body("PRODUCT");
        b.withArray("items").add(item(body("VENDOR")));
        assertTrue(
                guard.prepare(b).issues().stream()
                        .anyMatch(i -> i.row() == 1 && i.code().equals("KIND_MISMATCH")));
        for (String invalid : List.of("name\n", "\tname", "name\u2028", "bad\ud800")) {
            b = body("VENDOR");
            item(b).put("name", invalid);
            assertFalse(guard.prepare(b).issues().isEmpty());
        }
    }

    @Test
    void duplicateCanonicalIdsSourcesAndReferencesRejectRatherThanSilentlyDeduplicate() {
        var b = body("PRODUCT");
        ObjectNode next = item(b).deepCopy();
        next.put("id", ID.toUpperCase(Locale.ROOT));
        next.put("source_key", " source-1 ");
        b.withArray("items").add(next);
        var issues = guard.prepare(b).issues();
        assertEquals(
                List.of("DUPLICATE_ID", "DUPLICATE_SOURCE_KEY"),
                issues.stream().map(ReferenceImportGuard.Issue::code).toList());
        b = body("PRODUCT");
        item(b).withArray("data_owner_user_ids").add(OWNER.toUpperCase(Locale.ROOT));
        item(b).withArray("allowed_agent_ids").add(AGENT);
        assertEquals(
                2,
                guard.prepare(b).issues().stream()
                        .filter(i -> i.code().equals("DUPLICATE_REFERENCE"))
                        .count());
    }

    @Test
    void nfcCodePointsAndSortedSetsProduceStableNormalizedFingerprint() {
        var first = body("PRODUCT").put("source", "  Cafe\u0301 ").put("reason", "  正常原因 ");
        item(first).put("name", "😀".repeat(255));
        item(first).withArray("data_owner_user_ids").add(AGENT);
        var second = body("PRODUCT").put("source", "Café").put("reason", "正常原因");
        item(second).put("name", "😀".repeat(255));
        item(second)
                .putArray("data_owner_user_ids")
                .add(AGENT.toUpperCase(Locale.ROOT))
                .add(OWNER.toUpperCase(Locale.ROOT));
        var a = guard.prepare(first);
        var c = guard.prepare(second);
        assertTrue(a.issues().isEmpty());
        assertEquals(a.hash(), c.hash());
        assertEquals("Café", a.source());
        item(first).put("name", "😀".repeat(256));
        assertFalse(guard.prepare(first).issues().isEmpty());
        first.put("reason", "正文\n换行");
        failure(first, 422, "FIELD_VALIDATION_FAILED");
    }

    @Test
    void quantitiesRevisionAndTopTextBoundariesAreRequestErrors() {
        var b = body("VENDOR");
        b.putArray("items");
        failure(b, 422, "FIELD_VALIDATION_FAILED");
        b = body("VENDOR");
        ArrayNode rows = b.withArray("items");
        for (int i = 1; i < 500; i++) {
            ObjectNode n = item(b).deepCopy();
            n.put("id", new UUID(0, i).toString()).put("source_key", "row-" + i);
            rows.add(n);
        }
        assertEquals(500, guard.prepare(b).items().size());
        rows.add(item(b).deepCopy());
        failure(b, 422, "FIELD_VALIDATION_FAILED");
        for (long v : new long[] {-1, ReferenceImportGuard.MAX_REVISION + 1, Long.MAX_VALUE})
            failure(body("VENDOR").put("base_catalog_revision", v), 422, "FIELD_VALIDATION_FAILED");
        assertEquals(
                ReferenceImportGuard.MAX_REVISION,
                guard.prepare(
                                body("VENDOR")
                                        .put(
                                                "base_catalog_revision",
                                                ReferenceImportGuard.MAX_REVISION))
                        .baseRevision());
        failure(body("VENDOR").put("base_catalog_revision", 1.0), 400, "INVALID_STRUCTURE");
        failure(body("VENDOR").put("source", "x".repeat(256)), 422, "FIELD_VALIDATION_FAILED");
        failure(body("VENDOR").put("reason", "x".repeat(1001)), 422, "FIELD_VALIDATION_FAILED");
        assertTrue(
                guard.prepare(
                                body("VENDOR")
                                        .put("source", "x".repeat(255))
                                        .put("reason", "x".repeat(1000)))
                        .issues()
                        .isEmpty());
    }

    @Test
    void ownersAndAllowedAgentsHaveOneToFiveHundredStrictUniqueUuids() {
        for (String field : List.of("data_owner_user_ids", "allowed_agent_ids")) {
            var b = body("PRODUCT");
            ArrayNode values = item(b).putArray(field);
            assertFalse(guard.prepare(b).issues().isEmpty());
            for (int i = 0; i < 500; i++) values.add(new UUID(0, i).toString());
            assertTrue(guard.prepare(b).issues().isEmpty());
            values.add(new UUID(0, 501).toString());
            assertFalse(guard.prepare(b).issues().isEmpty());
        }
    }

    @Test
    void rawBodyLimitDuplicateKeysTrailingJsonAndMalformedEncodingAreRejected() throws Exception {
        byte[] valid = json.writeValueAsBytes(body("VENDOR"));
        assertTrue(guard.parse(valid).issues().isEmpty());
        byte[] maximum = Arrays.copyOf(valid, ReferenceImportGuard.MAX_BODY_BYTES);
        Arrays.fill(maximum, valid.length, maximum.length, (byte) ' ');
        assertTrue(guard.parse(maximum).issues().isEmpty());
        var tooLarge =
                assertThrows(
                        ReferenceImportGuard.Failure.class,
                        () -> guard.parse(Arrays.copyOf(maximum, maximum.length + 1)));
        assertEquals(413, tooLarge.status);
        for (String raw :
                List.of("{\"kind\":\"VENDOR\",\"kind\":\"PRODUCT\"}", "{} {}", "null", "[]", "{")) {
            var f =
                    assertThrows(
                            ReferenceImportGuard.Failure.class,
                            () -> guard.parse(raw.getBytes(StandardCharsets.UTF_8)));
            assertEquals(400, f.status);
        }
        assertEquals(
                400,
                assertThrows(
                                ReferenceImportGuard.Failure.class,
                                () -> guard.parse(new byte[] {(byte) 0xc3, (byte) 0x28}))
                        .status);
    }
}
