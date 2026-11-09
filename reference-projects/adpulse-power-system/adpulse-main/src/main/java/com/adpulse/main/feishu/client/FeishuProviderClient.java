package com.adpulse.main.feishu.client;

import com.adpulse.main.feishu.dto.FeishuDtos.FieldOption;
import com.adpulse.main.feishu.dto.FeishuDtos.TableOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** 飞书开放平台最小权限客户端，仅用于连接检查、子表和字段发现。 */
@Component
public class FeishuProviderClient {
    private final RestClient client =
            RestClient.builder().baseUrl("https://open.feishu.cn/open-apis").build();

    /** 验证应用凭证并返回租户令牌。 */
    public String tenantToken(String appId, String appSecret) {
        Map<?, ?> response =
                client.post()
                        .uri("/auth/v3/tenant_access_token/internal")
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(Map.of("app_id", appId, "app_secret", appSecret))
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        Object token = response == null ? null : response.get("tenant_access_token");
        if (token == null) throw new FeishuProviderException("飞书未返回tenant_access_token");
        return token.toString();
    }

    /** 查询多维表格全部子表。 */
    public List<TableOption> tables(String appId, String appSecret, String appToken) {
        String token = tenantToken(appId, appSecret);
        Map<?, ?> response =
                client.get()
                        .uri("/bitable/v1/apps/{appToken}/tables?page_size=100", appToken)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        Map<?, ?> data = response == null ? null : asMap(response.get("data"));
        List<?> items = data == null ? List.of() : asList(data.get("items"));
        List<TableOption> result = new ArrayList<>();
        for (Object value : items) {
            Map<?, ?> item = asMap(value);
            if (item != null)
                result.add(new TableOption(text(item.get("table_id")), text(item.get("name"))));
        }
        return result;
    }

    /** 查询多维表格字段。 */
    public List<FieldOption> fields(
            String appId, String appSecret, String appToken, String tableId) {
        String token = tenantToken(appId, appSecret);
        Map<?, ?> response =
                client.get()
                        .uri(
                                "/bitable/v1/apps/{appToken}/tables/{tableId}/fields?page_size=100",
                                appToken,
                                tableId)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .body(Map.class);
        requireSuccess(response);
        Map<?, ?> data = response == null ? null : asMap(response.get("data"));
        List<?> items = data == null ? List.of() : asList(data.get("items"));
        List<FieldOption> result = new ArrayList<>();
        for (Object value : items) {
            Map<?, ?> item = asMap(value);
            if (item != null) {
                String name = text(item.get("field_name"));
                result.add(new FieldOption(name, name));
            }
        }
        return result;
    }

    private void requireSuccess(Map<?, ?> response) {
        if (response == null || !"0".equals(text(response.get("code"))))
            throw new FeishuProviderException(
                    response == null ? "飞书接口无响应" : text(response.get("msg")));
    }

    private Map<?, ?> asMap(Object value) {
        return value instanceof Map<?, ?> map ? map : null;
    }

    private List<?> asList(Object value) {
        return value instanceof List<?> list ? list : List.of();
    }

    private String text(Object value) {
        return value == null ? "" : value.toString();
    }

    /** 飞书开放平台调用异常。 */
    public static class FeishuProviderException extends RuntimeException {
        /** 创建飞书开放平台调用异常。 */
        public FeishuProviderException(String message) {
            super(message);
        }
    }
}
