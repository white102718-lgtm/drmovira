package com.ruoyi.system.orbit.scope;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 范围请求白名单、模式互斥与数量边界，不接受客户端伪造成员。 */
public class ScopeRequestGuardTest {
    private final ObjectMapper json = new ObjectMapper();
    private final ScopeRequestGuard guard = new ScopeRequestGuard(json);

    public static ObjectNode filter(ObjectMapper json) {
        ObjectNode root = json.createObjectNode().put("mode", "FILTER");
        root.putArray("account_ids");
        root.putObject("filter")
                .put("q", "")
                .putNull("status")
                .putNull("auth_status")
                .putNull("operator_user_id")
                .putNull("vendor_id");
        return root;
    }

    public static ObjectNode ids(ObjectMapper json, String... values) {
        ObjectNode root = json.createObjectNode().put("mode", "IDS");
        var ids = root.putArray("account_ids");
        for (String value : values) ids.add(value);
        root.putNull("filter");
        return root;
    }

    @ParameterizedTest
    @ValueSource(strings = {"mode", "account_ids", "filter"})
    void requiresAllTopLevelFields(String field) {
        ObjectNode body = filter(json);
        body.remove(field);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(body));
    }

    @ParameterizedTest
    @ValueSource(strings = {"q", "status", "auth_status", "operator_user_id", "vendor_id"})
    void requiresAllFilterFieldsEvenWhenNull(String field) {
        ObjectNode body = filter(json);
        ((ObjectNode) body.get("filter")).remove(field);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(body));
    }

    @ParameterizedTest
    @ValueSource(strings = {"tenant_id", "actor_id", "members", "external_id", "name"})
    void cannotInjectServerIdentityOrMemberData(String field) {
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(filter(json).put(field, "injected")));
    }

    @Test
    void modesAreExclusiveAndRequireExpectedContainers() {
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(ids(json)));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(filter(json).putNull("filter")));
        ObjectNode mixed = filter(json);
        ((com.fasterxml.jackson.databind.node.ArrayNode) mixed.get("account_ids"))
                .add(UUID.randomUUID().toString());
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(mixed));
        assertThrows(
                IllegalArgumentException.class,
                () ->
                        guard.prepare(
                                ids(json, UUID.randomUUID().toString())
                                        .set("filter", json.createObjectNode())));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(filter(json).put("mode", "SQL")));
        assertThrows(
                IllegalArgumentException.class,
                () -> guard.prepare(filter(json).put("account_ids", "not-array")));
    }

    @Test
    void idsAreNormalizedDeduplicatedSortedAndFrozen() {
        String a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
        ObjectNode source = ids(json, b, a.toUpperCase(Locale.ROOT), a);
        var selection = guard.prepare(source);
        assertEquals(List.of(a, b), selection.accountIds());
        assertThrows(UnsupportedOperationException.class, () -> selection.accountIds().clear());
        ((com.fasterxml.jackson.databind.node.ArrayNode) source.get("account_ids")).removeAll();
        assertEquals(2, selection.accountIds().size());
        assertEquals(guard.prepare(ids(json, a, b)).canonical(), selection.canonical());
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(ids(json, "1-1-1-1-1")));
    }

    @Test
    void enforcesRaw50000CapWithoutTruncating() {
        ObjectNode body = ids(json);
        var array = (com.fasterxml.jackson.databind.node.ArrayNode) body.get("account_ids");
        for (int i = 0; i < 50000; i++) array.add(new UUID(0, i + 1).toString());
        assertEquals(50000, guard.prepare(body).accountIds().size());
        array.add(new UUID(0, 50001).toString());
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(body));
    }

    @ParameterizedTest
    @ValueSource(strings = {"ACTIVE", "DISABLED", "UNKNOWN"})
    void acceptsEachAccountStatus(String status) {
        ObjectNode body = filter(json);
        ((ObjectNode) body.get("filter")).put("status", status);
        assertEquals(status, guard.prepare(body).status());
    }

    @ParameterizedTest
    @ValueSource(strings = {"AUTHORIZED", "EXPIRED", "REVOKED", "UNKNOWN"})
    void acceptsEachAuthorizationStatus(String status) {
        ObjectNode body = filter(json);
        ((ObjectNode) body.get("filter")).put("auth_status", status);
        assertEquals(status, guard.prepare(body).authStatus());
    }

    @Test
    void rejectsUnknownFiltersInvalidTypesAndUnboundedText() {
        for (String field : List.of("status", "auth_status", "operator_user_id", "vendor_id")) {
            ObjectNode bad = filter(json);
            ((ObjectNode) bad.get("filter")).put(field, "invalid");
            assertThrows(IllegalArgumentException.class, () -> guard.prepare(bad));
        }
        ObjectNode extra = filter(json);
        ((ObjectNode) extra.get("filter")).put("sql", "ignored?");
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(extra));
        ObjectNode longQuery = filter(json);
        ((ObjectNode) longQuery.get("filter")).put("q", "😀".repeat(101));
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(longQuery));
        ObjectNode typed = filter(json);
        ((ObjectNode) typed.get("filter")).put("q", 1);
        assertThrows(IllegalArgumentException.class, () -> guard.prepare(typed));
    }

    @Test
    void likeMetacharactersAreEscapedAsLiteralSearch() {
        ObjectNode body = filter(json);
        ((ObjectNode) body.get("filter")).put("q", "  !%_  ");
        var selection = guard.prepare(body);
        assertEquals("!%_", selection.q());
        assertEquals("!!!%!_", selection.escapedQ());
    }

    @Test
    void projectedFieldsMatchUnmodifiedProductContract() throws Exception {
        var schema =
                json.readTree(
                                Files.readString(
                                        Path.of(
                                                "../docs/orbit/baseline/contracts/openapi-current.json")))
                        .path("components")
                        .path("schemas");
        Set<String> expected = new HashSet<>(), actual = new HashSet<>();
        schema.path("ScopeRequest").path("properties").fieldNames().forEachRemaining(expected::add);
        filter(json).fieldNames().forEachRemaining(actual::add);
        assertEquals(expected, actual);
        assertEquals(
                50000,
                schema.path("ScopeRequest")
                        .path("properties")
                        .path("account_ids")
                        .path("maxItems")
                        .asInt());
    }
}
