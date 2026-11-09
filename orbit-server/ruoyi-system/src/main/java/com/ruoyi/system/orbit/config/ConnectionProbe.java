package com.ruoyi.system.orbit.config;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import org.springframework.stereotype.Component;

/** 只访问固定官方域名的只读认证探测，不生成AI内容、不创建或修改广告。 */
@Component
public class ConnectionProbe {
    /** 探测结果不含第三方原始响应，不能被当作生成质量或广告写能力证据。 */
    public record Result(String status, String message) {}

    private final HttpClient client;
    private final ObjectMapper mapper;

    @org.springframework.beans.factory.annotation.Autowired
    public ConnectionProbe(ObjectMapper mapper) {
        this(
                mapper,
                HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(5))
                        .followRedirects(HttpClient.Redirect.NEVER)
                        .build());
    }

    ConnectionProbe(ObjectMapper mapper, HttpClient client) {
        this.mapper = mapper;
        this.client = client;
    }

    /** 仅四种有固定只读接口的凭据支持此探测，其余由对应连接器实测。 */
    public Result check(String section, Map<String, Object> settings, Map<String, String> secrets) {
        String path;
        String bearer;
        HttpRequest.Builder request;
        switch (section) {
            case "AI_GPT" -> {
                path = "https://api.openai.com/v1/models/" + encode(settings.get("model"));
                bearer = secrets.get("apiKey");
                request = HttpRequest.newBuilder(URI.create(path));
            }
            case "AI_CLAUDE" -> {
                path = "https://api.anthropic.com/v1/models/" + encode(settings.get("model"));
                bearer = secrets.get("apiKey");
                request =
                        HttpRequest.newBuilder(URI.create(path))
                                .header("anthropic-version", settings.get("apiVersion").toString());
                String workspace = settings.getOrDefault("workspaceId", "").toString();
                if (!workspace.isBlank()) {
                    request.header("anthropic-workspace-id", workspace);
                }
            }
            case "META_BM" -> {
                path =
                        "https://graph.facebook.com/"
                                + settings.get("graphVersion")
                                + "/"
                                + settings.get("businessId")
                                + "?fields=id,name";
                bearer = secrets.get("accessToken");
                request = HttpRequest.newBuilder(URI.create(path));
            }
            case "META_APP" -> {
                path =
                        "https://graph.facebook.com/"
                                + settings.get("graphVersion")
                                + "/"
                                + settings.get("appId")
                                + "?fields=id,name";
                String appSecret = secrets.get("appSecret");
                // 缺失凭据不能拼成AppID|null后误发请求；停用草稿也必须明确阻断。
                if (appSecret == null || appSecret.isBlank()) {
                    return new Result("BLOCKED", "尚未配置必需凭据");
                }
                bearer = settings.get("appId") + "|" + appSecret;
                request = HttpRequest.newBuilder(URI.create(path));
            }
            default -> {
                return new Result("BLOCKED", "此配置须由对应业务连接器验证；当前未进行真实连接测试");
            }
        }
        if (bearer == null || bearer.isBlank()) {
            return new Result("BLOCKED", "尚未配置必需凭据");
        }
        try {
            HttpResponse<InputStream> response =
                    client.send(
                            request.GET()
                                    .header("Authorization", "Bearer " + bearer)
                                    .timeout(Duration.ofSeconds(15))
                                    .build(),
                            HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream stream = response.body()) {
                if (response.statusCode() == 401 || response.statusCode() == 403) {
                    return new Result("FAILED", "凭据无效、已过期或没有目标对象读取权限");
                }
                if (response.statusCode() == 429) {
                    return new Result("FAILED", "平台限制请求频率，请稍后重新测试");
                }
                if (response.statusCode() != 200) {
                    return new Result("FAILED", "平台未通过只读验证，请检查模型、版本和目标授权");
                }
                byte[] bytes = stream.readNBytes(1_048_577);
                if (bytes.length > 1_048_576) {
                    return new Result("FAILED", "平台响应超过安全限制");
                }
                JsonNode body = mapper.readTree(bytes);
                if (!body.path("id").isTextual() || body.path("id").asText().isBlank()) {
                    return new Result("FAILED", "平台返回的只读证据不完整");
                }
                // Meta对象标识须逐配置匹配，不能用其他应用/BM的证据认证当前对象。
                String targetId =
                        switch (section) {
                            case "META_BM" -> settings.get("businessId").toString();
                            case "META_APP" -> settings.get("appId").toString();
                            default -> null; // AI模型可能返回官方规范ID，不按用户输入的模型别名强制相等。
                        };
                if (targetId != null && !body.path("id").asText().equals(targetId)) {
                    return new Result("FAILED", "平台返回对象与配置的Meta目标不一致");
                }
                return new Result("READ_VERIFIED", "只读认证通过；尚未验证AI建议生成或广告写操作能力");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return new Result("FAILED", "连接测试已中断");
        } catch (Exception exception) {
            // 不记录HttpRequest/异常堆栈或响应，避免Authorization进入错误详情。
            return new Result("FAILED", "连接测试失败或超时，请检查网络与平台配置");
        }
    }

    private static String encode(Object value) {
        return URLEncoder.encode(value.toString(), StandardCharsets.UTF_8);
    }
}
