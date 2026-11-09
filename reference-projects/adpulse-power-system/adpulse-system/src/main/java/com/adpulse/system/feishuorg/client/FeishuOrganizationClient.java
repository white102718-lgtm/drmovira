package com.adpulse.system.feishuorg.client;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.DepartmentRecord;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot.UserRecord;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

/** 飞书通讯录只读客户端，负责令牌、分页以及响应校验。 */
@Component
public class FeishuOrganizationClient {

    static final String TENANT_ROOT_EXTERNAL_ID = "TENANT_ROOT";
    private static final String FEISHU_ROOT_DEPARTMENT_ID = "0";

    private final FeishuOrganizationMapper mapper;
    private final FeishuSecretCipher cipher;
    private final RestClient client;

    @Autowired
    public FeishuOrganizationClient(FeishuOrganizationMapper mapper, FeishuSecretCipher cipher) {
        this(mapper, cipher, productionBuilder());
    }

    FeishuOrganizationClient(
            FeishuOrganizationMapper mapper,
            FeishuSecretCipher cipher,
            RestClient.Builder clientBuilder) {
        this.mapper = mapper;
        this.cipher = cipher;
        this.client = clientBuilder.baseUrl("https://open.feishu.cn/open-apis").build();
    }

    /** 读取企业信息以及根部门下的部门与人员完整快照。 */
    public FeishuOrganizationSnapshot fetchSnapshot() {
        long deadline = System.nanoTime() + Duration.ofMinutes(10).toNanos();
        FeishuApplicationConfig configuration = requireConfiguration();
        String appSecret = cipher.decrypt(configuration.getAppSecretCiphertext());
        String token = tenantToken(configuration.getAppId(), appSecret);
        TenantInfo tenant = fetchTenant(token);
        List<DepartmentRecord> remoteDepartments =
                fetchDepartments(token, FEISHU_ROOT_DEPARTMENT_ID, deadline);
        List<DepartmentRecord> departments = new ArrayList<>();
        departments.add(
                new DepartmentRecord(
                        TENANT_ROOT_EXTERNAL_ID,
                        FEISHU_ROOT_DEPARTMENT_ID,
                        tenant.name(),
                        0,
                        null));
        remoteDepartments.stream().map(this::underTenantRoot).forEach(departments::add);
        Map<String, UserRecord> users = new LinkedHashMap<>();
        List<String> departmentIds = new ArrayList<>();
        departmentIds.add(FEISHU_ROOT_DEPARTMENT_ID);
        remoteDepartments.stream().map(DepartmentRecord::departmentId).forEach(departmentIds::add);
        for (String departmentId : departmentIds) {
            fetchUsers(token, departmentId, deadline).stream()
                    .map(this::underTenantRoot)
                    .forEach(user -> users.put(user.userId(), user));
        }
        return new FeishuOrganizationSnapshot(
                tenant.tenantKey(), departments, List.copyOf(users.values()));
    }

    /** 按手机号查询飞书 open_id，供测试环境固定收件人缺少本地同步记录时使用。 */
    public List<String> findOpenIdsByMobile(String mobile) {
        if (!StringUtils.hasText(mobile)) return List.of();

        FeishuApplicationConfig configuration = requireConfiguration();
        String appSecret = cipher.decrypt(configuration.getAppSecretCiphertext());
        String token = tenantToken(configuration.getAppId(), appSecret);
        Map<?, ?> response =
                client.post()
                        .uri("/contact/v3/users/batch_get_id?user_id_type=open_id")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("mobiles", List.of(mobile)))
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        Map<?, ?> data = map(response == null ? null : response.get("data"));
        return list(data == null ? null : data.get("user_list")).stream()
                .map(this::map)
                .filter(java.util.Objects::nonNull)
                .map(user -> text(user.get("user_id")))
                .filter(StringUtils::hasText)
                .distinct()
                .toList();
    }

    private TenantInfo fetchTenant(String token) {
        Map<?, ?> response =
                client.get()
                        .uri("/tenant/v2/tenant/query")
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        Map<?, ?> data = map(response == null ? null : response.get("data"));
        Map<?, ?> tenant = map(data == null ? null : data.get("tenant"));
        String tenantKey = text(tenant == null ? null : tenant.get("tenant_key"));
        String name = text(tenant == null ? null : tenant.get("name"));
        if (!StringUtils.hasText(tenantKey) || !StringUtils.hasText(name)) {
            throw BusinessException.conflict("飞书未返回完整的企业名称和租户标识");
        }
        return new TenantInfo(tenantKey, name);
    }

    private DepartmentRecord underTenantRoot(DepartmentRecord department) {
        return FEISHU_ROOT_DEPARTMENT_ID.equals(department.parentDepartmentId())
                ? new DepartmentRecord(
                        department.departmentId(),
                        TENANT_ROOT_EXTERNAL_ID,
                        department.name(),
                        department.order(),
                        department.leaderUserId())
                : department;
    }

    private UserRecord underTenantRoot(UserRecord user) {
        return new UserRecord(
                user.userId(),
                user.openId(),
                user.unionId(),
                user.name(),
                user.mobile(),
                user.email(),
                user.avatarUrl(),
                user.active(),
                user.departmentIds().stream()
                        .map(
                                departmentId ->
                                        FEISHU_ROOT_DEPARTMENT_ID.equals(departmentId)
                                                ? TENANT_ROOT_EXTERNAL_ID
                                                : departmentId)
                        .toList());
    }

    private String tenantToken(String appId, String appSecret) {
        Map<?, ?> response =
                client.post()
                        .uri("/auth/v3/tenant_access_token/internal")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("app_id", appId, "app_secret", appSecret))
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        String token = text(response == null ? null : response.get("tenant_access_token"));
        if (!StringUtils.hasText(token)) {
            throw BusinessException.conflict("飞书未返回租户访问令牌");
        }
        return token;
    }

    private List<DepartmentRecord> fetchDepartments(String token, String rootId, long deadline) {
        List<DepartmentRecord> result = new ArrayList<>();
        Set<String> pages = new HashSet<>();
        String pageToken = null;
        do {
            checkDeadline(deadline);
            String currentPageToken = pageToken;
            Map<?, ?> response =
                    client.get()
                            .uri(
                                    builder -> {
                                        builder.path(
                                                        "/contact/v3/departments/{departmentId}/children")
                                                .queryParam("department_id_type", "department_id")
                                                .queryParam("fetch_child", true)
                                                .queryParam("page_size", 50);
                                        if (StringUtils.hasText(currentPageToken)) {
                                            builder.queryParam("page_token", currentPageToken);
                                        }
                                        return builder.build(rootId);
                                    })
                            .header("Authorization", "Bearer " + token)
                            .retrieve()
                            .body(Map.class);
            requireSuccess(response);
            Map<?, ?> data = pageData(response);
            for (Object value : list(data == null ? null : data.get("items"))) {
                Map<?, ?> item = map(value);
                if (item == null) throw BusinessException.conflict("飞书部门数据格式不完整");
                List<?> leaders = list(item.get("leaders"));
                String leaderId =
                        leaders.isEmpty() ? null : text(map(leaders.getFirst()).get("leader_id"));
                String parentDepartmentId = text(item.get("parent_department_id"));
                result.add(
                        new DepartmentRecord(
                                text(item.get("department_id")),
                                rootId.equals(parentDepartmentId) ? "0" : parentDepartmentId,
                                text(item.get("name")),
                                integer(item.get("order")),
                                leaderId));
            }
            pageToken = nextPage(data, pages);
        } while (StringUtils.hasText(pageToken));
        return result;
    }

    private List<UserRecord> fetchUsers(String token, String departmentId, long deadline) {
        List<UserRecord> result = new ArrayList<>();
        Set<String> pages = new HashSet<>();
        String pageToken = null;
        do {
            checkDeadline(deadline);
            String currentPageToken = pageToken;
            Map<?, ?> response =
                    client.get()
                            .uri(
                                    builder -> {
                                        builder.path("/contact/v3/users/find_by_department")
                                                .queryParam("department_id", departmentId)
                                                .queryParam("department_id_type", "department_id")
                                                .queryParam("user_id_type", "user_id")
                                                .queryParam("page_size", 50);
                                        if (StringUtils.hasText(currentPageToken)) {
                                            builder.queryParam("page_token", currentPageToken);
                                        }
                                        return builder.build();
                                    })
                            .header("Authorization", "Bearer " + token)
                            .retrieve()
                            .body(Map.class);
            requireSuccess(response);
            Map<?, ?> data = pageData(response);
            for (Object value : list(data == null ? null : data.get("items"))) {
                Map<?, ?> item = map(value);
                if (item == null) throw BusinessException.conflict("飞书人员数据格式不完整");
                Map<?, ?> avatar = map(item.get("avatar"));
                Map<?, ?> status = map(item.get("status"));
                if (status == null || !(status.get("is_activated") instanceof Boolean)) {
                    throw BusinessException.conflict("飞书人员状态缺失，本次快照已丢弃");
                }
                result.add(
                        new UserRecord(
                                text(item.get("user_id")),
                                text(item.get("open_id")),
                                text(item.get("union_id")),
                                text(item.get("name")),
                                blankToNull(text(item.get("mobile"))),
                                blankToNull(text(item.get("email"))),
                                blankToNull(text(avatar == null ? null : avatar.get("avatar_240"))),
                                status != null
                                        && Boolean.TRUE.equals(status.get("is_activated"))
                                        && !Boolean.TRUE.equals(status.get("is_frozen"))
                                        && !Boolean.TRUE.equals(status.get("is_resigned"))
                                        && !Boolean.TRUE.equals(status.get("is_exited")),
                                list(item.get("department_ids")).stream()
                                        .map(this::text)
                                        .filter(StringUtils::hasText)
                                        .toList()));
            }
            pageToken = nextPage(data, pages);
        } while (StringUtils.hasText(pageToken));
        return result;
    }

    private FeishuApplicationConfig requireConfiguration() {
        FeishuApplicationConfig configuration = mapper.findApplicationConfig();
        if (configuration == null
                || !StringUtils.hasText(configuration.getAppId())
                || !StringUtils.hasText(configuration.getAppSecretCiphertext())) {
            throw BusinessException.conflict("请先配置飞书应用");
        }
        return configuration;
    }

    private static RestClient.Builder productionBuilder() {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(10));
        factory.setReadTimeout(Duration.ofSeconds(30));
        return RestClient.builder().requestFactory(factory);
    }

    private void checkDeadline(long deadline) {
        if (Thread.currentThread().isInterrupted() || System.nanoTime() >= deadline) {
            throw BusinessException.conflict("飞书组织读取超时，本次快照已丢弃");
        }
    }

    private Map<?, ?> pageData(Map<?, ?> response) {
        Map<?, ?> data = map(response.get("data"));
        if (data == null
                || !(data.get("has_more") instanceof Boolean)
                || (data.get("items") != null && !(data.get("items") instanceof List<?>))) {
            throw BusinessException.conflict("飞书分页响应不完整，本次快照已丢弃");
        }
        return data;
    }

    private String nextPage(Map<?, ?> data, Set<String> pages) {
        if (!Boolean.TRUE.equals(data.get("has_more"))) return null;
        String token = text(data.get("page_token"));
        if (!StringUtils.hasText(token) || !pages.add(token)) {
            throw BusinessException.conflict("飞书分页标识缺失或重复，本次快照已丢弃");
        }
        return token;
    }

    private void requireSuccess(Map<?, ?> response) {
        if (response == null || !"0".equals(text(response.get("code")))) {
            throw BusinessException.conflict(response == null ? "飞书接口无响应" : "飞书接口返回失败，请检查应用权限与配置");
        }
    }

    private Map<?, ?> map(Object value) {
        return value instanceof Map<?, ?> result ? result : null;
    }

    private List<?> list(Object value) {
        return value instanceof List<?> result ? result : List.of();
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    private int integer(Object value) {
        try {
            return value == null ? 0 : Integer.parseInt(value.toString());
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private String blankToNull(String value) {
        return StringUtils.hasText(value) ? value : null;
    }

    private record TenantInfo(String tenantKey, String name) {}
}
