package com.adpulse.main.google.client;

import com.adpulse.main.google.config.GoogleIntegrationProperties;
import com.adpulse.main.google.dto.GoogleDtos.DriveFile;
import com.adpulse.main.google.dto.GoogleDtos.SheetTab;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;

/** Google OAuth、Drive和Sheets REST客户端。 */
@Component
public class GoogleProviderClient {
    private static final Pattern UPDATED_ROW = Pattern.compile("![A-Z]+(\\d+)(?::[A-Z]+\\d+)?$");
    private final GoogleIntegrationProperties properties;
    private final RestClient client = RestClient.create();

    public GoogleProviderClient(GoogleIntegrationProperties properties) {
        this.properties = properties;
    }

    /** 生成Google OAuth授权地址。 */
    public String authorizeUrl(String state) {
        requireConfigured();
        return UriComponentsBuilder.fromUriString("https://accounts.google.com/o/oauth2/v2/auth")
                .queryParam("client_id", properties.clientId())
                .queryParam("redirect_uri", properties.redirectUri())
                .queryParam("response_type", "code")
                .queryParam(
                        "scope",
                        "openid email profile https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets.readonly")
                .queryParam("access_type", "offline")
                .queryParam("prompt", "consent")
                .queryParam("state", state)
                .build()
                .encode()
                .toUriString();
    }

    /** 使用授权码交换访问令牌。 */
    public Token exchange(String code) {
        requireConfigured();
        var form = new LinkedMultiValueMap<String, String>();
        form.add("code", code);
        form.add("client_id", properties.clientId());
        form.add("client_secret", properties.clientSecret());
        form.add("redirect_uri", properties.redirectUri());
        form.add("grant_type", "authorization_code");
        return token(
                client.post()
                        .uri("https://oauth2.googleapis.com/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body(form)
                        .retrieve()
                        .body(Map.class));
    }

    /** 使用刷新令牌获取新的访问令牌。 */
    public Token refresh(String refreshToken) {
        requireConfigured();
        var form = new LinkedMultiValueMap<String, String>();
        form.add("refresh_token", refreshToken);
        form.add("client_id", properties.clientId());
        form.add("client_secret", properties.clientSecret());
        form.add("grant_type", "refresh_token");
        return token(
                client.post()
                        .uri("https://oauth2.googleapis.com/token")
                        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                        .body(form)
                        .retrieve()
                        .body(Map.class));
    }

    /** 查询Google用户稳定标识与展示资料。 */
    public UserInfo userInfo(String accessToken) {
        Map<?, ?> data = get("https://www.googleapis.com/oauth2/v3/userinfo", accessToken);
        return new UserInfo(
                text(data.get("sub")), text(data.get("email")), text(data.get("picture")));
    }

    /** 查询账号可访问的Google Sheets文件。 */
    public List<DriveFile> files(String accessToken, String keyword) {
        String q = "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false";
        if (keyword != null && !keyword.isBlank())
            q += " and name contains '" + keyword.replace("'", "\\'") + "'";
        URI uri =
                UriComponentsBuilder.fromUriString("https://www.googleapis.com/drive/v3/files")
                        .queryParam("q", q)
                        .queryParam("spaces", "drive")
                        .queryParam("corpora", "user")
                        .queryParam("supportsAllDrives", true)
                        .queryParam("includeItemsFromAllDrives", true)
                        .queryParam("fields", "files(id,name,modifiedTime)")
                        .queryParam("pageSize", 100)
                        .build()
                        .encode()
                        .toUri();
        Map<?, ?> data = get(uri, accessToken);
        List<DriveFile> result = new ArrayList<>();
        for (Object value : list(data.get("files"))) {
            Map<?, ?> item = map(value);
            if (item != null)
                result.add(
                        new DriveFile(
                                text(item.get("id")),
                                text(item.get("name")),
                                text(item.get("modifiedTime"))));
        }
        return result;
    }

    /** 按稳定ID读取单个Google Sheets文件，适用于从业务链接直接定位目标。 */
    public DriveFile file(String accessToken, String fileId) {
        URI uri =
                UriComponentsBuilder.fromUriString(
                                "https://www.googleapis.com/drive/v3/files/{fileId}")
                        .queryParam("fields", "id,name,modifiedTime,mimeType")
                        .queryParam("supportsAllDrives", true)
                        .buildAndExpand(fileId)
                        .encode()
                        .toUri();
        Map<?, ?> data = get(uri, accessToken);
        if (!"application/vnd.google-apps.spreadsheet".equals(text(data.get("mimeType"))))
            throw new GoogleProviderException("业务链接不是Google Sheets文件");
        return new DriveFile(
                text(data.get("id")), text(data.get("name")), text(data.get("modifiedTime")));
    }

    /** 查询Spreadsheet全部Sheet名称。 */
    public List<SheetTab> sheets(String accessToken, String fileId) {
        Map<?, ?> data =
                get(
                        "https://sheets.googleapis.com/v4/spreadsheets/"
                                + fileId
                                + "?fields=sheets.properties(sheetId,title)",
                        accessToken);
        List<SheetTab> result = new ArrayList<>();
        for (Object value : list(data.get("sheets"))) {
            Map<?, ?> sheet = map(value);
            Map<?, ?> props = sheet == null ? null : map(sheet.get("properties"));
            if (props != null)
                result.add(new SheetTab(text(props.get("sheetId")), text(props.get("title"))));
        }
        return result;
    }

    /** 查询Sheet第一行作为字段名称，供现有Google数据同步功能使用。 */
    public List<String> columns(String accessToken, String fileId, String sheetName) {
        return columns(accessToken, fileId, sheetName, 1);
    }

    /** 查询Sheet指定行作为字段名称。 */
    public List<String> columns(
            String accessToken, String fileId, String sheetName, int headerRow) {
        String range = quoteSheet(sheetName) + "!" + headerRow + ":" + headerRow;
        URI uri =
                UriComponentsBuilder.fromUriString("https://sheets.googleapis.com")
                        .pathSegment("v4", "spreadsheets", fileId, "values", range)
                        .build()
                        .encode()
                        .toUri();
        Map<?, ?> data = get(uri, accessToken);
        List<?> rows = list(data.get("values"));
        if (rows.isEmpty()) return List.of();
        return list(rows.getFirst()).stream().map(this::text).toList();
    }

    /** 读取指定Sheet的全部单元格数据。 */
    public List<List<String>> values(String accessToken, String fileId, String sheetName) {
        return valuesRange(accessToken, fileId, quoteSheet(sheetName));
    }

    /** 读取Sheet已使用区域的原始值，供联合唯一键进行稳定匹配。 */
    public List<List<Object>> rawValues(String accessToken, String fileId, String sheetName) {
        URI uri =
                UriComponentsBuilder.fromUriString("https://sheets.googleapis.com")
                        .pathSegment(
                                "v4", "spreadsheets", fileId, "values", quoteSheet(sheetName))
                        .queryParam("valueRenderOption", "UNFORMATTED_VALUE")
                        .queryParam("dateTimeRenderOption", "FORMATTED_STRING")
                        .build()
                        .encode()
                        .toUri();
        Map<?, ?> data = get(uri, accessToken);
        List<List<Object>> result = new ArrayList<>();
        for (Object rowValue : list(data.get("values"))) {
            result.add(new ArrayList<>(list(rowValue)));
        }
        return result;
    }

    /** 读取指定A1范围。 */
    public List<List<String>> valuesRange(String accessToken, String fileId, String range) {
        URI uri =
                UriComponentsBuilder.fromUriString("https://sheets.googleapis.com")
                        .pathSegment("v4", "spreadsheets", fileId, "values", range)
                        .build()
                        .encode()
                        .toUri();
        Map<?, ?> data = get(uri, accessToken);
        List<List<String>> result = new ArrayList<>();
        for (Object rowValue : list(data.get("values"))) {
            result.add(list(rowValue).stream().map(this::text).toList());
        }
        return result;
    }

    /** 在目标表格末尾追加一行并返回Google实际写入的行号。 */
    public int appendValues(
            String accessToken, String fileId, String sheetName, List<Object> rowValues) {
        String range = quoteSheet(sheetName) + "!A:ZZ";
        URI uri =
                UriComponentsBuilder.fromUriString(
                                "https://sheets.googleapis.com/v4/spreadsheets/{fileId}/values/{range}:append")
                        .queryParam("valueInputOption", "RAW")
                        .queryParam("insertDataOption", "INSERT_ROWS")
                        .buildAndExpand(fileId, range)
                        .encode()
                        .toUri();
        Map<?, ?> result = post(uri, accessToken, Map.of("values", List.of(rowValues)));
        Map<?, ?> updates = map(result.get("updates"));
        String updatedRange = updates == null ? "" : text(updates.get("updatedRange"));
        Matcher matcher = UPDATED_ROW.matcher(updatedRange);
        if (!matcher.find()) throw new GoogleProviderException("Google未返回新增行位置");
        return Integer.parseInt(matcher.group(1));
    }

    /** 清除指定行的用户格式，避免首条数据继承表头的加粗、背景色等样式。 */
    public void clearRowFormat(
            String accessToken, String fileId, String sheetId, int rowNumber) {
        Map<String, Object> range =
                Map.of(
                        "sheetId", Integer.parseInt(sheetId),
                        "startRowIndex", rowNumber - 1,
                        "endRowIndex", rowNumber);
        Map<String, Object> repeatCell =
                Map.of(
                        "range", range,
                        "cell", Map.of("userEnteredFormat", Map.of()),
                        "fields", "userEnteredFormat");
        URI uri =
                UriComponentsBuilder.fromUriString(
                                "https://sheets.googleapis.com/v4/spreadsheets/{fileId}:batchUpdate")
                        .buildAndExpand(fileId)
                        .encode()
                        .toUri();
        post(uri, accessToken, Map.of("requests", List.of(Map.of("repeatCell", repeatCell))));
    }

    /** 只更新已映射单元格，避免覆盖客户表格中的公式列和人工列。 */
    public void updateValues(
            String accessToken,
            String fileId,
            String sheetName,
            int rowNumber,
            Map<String, Object> fieldValues) {
        List<Map<String, Object>> data = new ArrayList<>();
        for (var entry : fieldValues.entrySet()) {
            Map<String, Object> cell = new LinkedHashMap<>();
            cell.put("range", quoteSheet(sheetName) + "!" + entry.getKey() + rowNumber);
            cell.put("values", List.of(List.of(entry.getValue())));
            data.add(cell);
        }
        URI uri =
                UriComponentsBuilder.fromUriString(
                                "https://sheets.googleapis.com/v4/spreadsheets/{fileId}/values:batchUpdate")
                        .buildAndExpand(fileId)
                        .encode()
                        .toUri();
        post(uri, accessToken, Map.of("valueInputOption", "RAW", "data", data));
    }

    private Map<?, ?> get(String uri, String token) {
        return get(URI.create(uri), token);
    }

    private Map<?, ?> get(URI uri, String token) {
        Map<?, ?> result =
                client.get()
                        .uri(uri)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .body(Map.class);
        if (result == null) throw new GoogleProviderException("Google接口无响应");
        return result;
    }

    private Map<?, ?> post(URI uri, String token, Object body) {
        Map<?, ?> result =
                client.post()
                        .uri(uri)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(body)
                        .retrieve()
                        .body(Map.class);
        if (result == null) throw new GoogleProviderException("Google接口无响应");
        return result;
    }

    private String quoteSheet(String sheetName) {
        return "'" + sheetName.replace("'", "''") + "'";
    }

    private Token token(Map<?, ?> data) {
        if (data == null || data.get("access_token") == null)
            throw new GoogleProviderException("Google未返回访问令牌");
        return new Token(
                text(data.get("access_token")),
                text(data.get("refresh_token")),
                number(data.get("expires_in")));
    }

    private void requireConfigured() {
        if (properties.clientId() == null
                || properties.clientId().isBlank()
                || properties.clientSecret() == null
                || properties.clientSecret().isBlank()
                || properties.redirectUri() == null
                || properties.redirectUri().isBlank())
            throw new GoogleProviderException("测试环境尚未配置Google OAuth凭证");
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

    private long number(Object value) {
        return value instanceof Number number ? number.longValue() : 3600;
    }

    /** Google令牌响应。 */
    public record Token(String accessToken, String refreshToken, long expiresIn) {}

    /** Google用户资料。 */
    public record UserInfo(String subject, String email, String picture) {}

    /** Google开放平台调用异常。 */
    public static class GoogleProviderException extends RuntimeException {
        /** 创建Google开放平台调用异常。 */
        public GoogleProviderException(String message) {
            super(message);
        }
    }
}
