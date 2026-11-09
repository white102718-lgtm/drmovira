package com.adpulse.main.deliveryreport.google;

import com.adpulse.main.deliveryreport.DeliveryReportException;
import com.adpulse.main.google.config.GoogleServiceAccountProperties;
import com.google.auth.oauth2.AccessToken;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ServiceAccountCredentials;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import org.springframework.stereotype.Component;

/** 为投放日报提供独立的Google服务账户访问令牌。 */
@Component
public class DeliveryReportGoogleServiceAccount {
    private static final List<String> SCOPES =
            List.of(
                    "https://www.googleapis.com/auth/drive.readonly",
                    "https://www.googleapis.com/auth/spreadsheets");

    private final GoogleServiceAccountProperties properties;
    private GoogleCredentials credentials;
    private String serviceAccountEmail;

    public DeliveryReportGoogleServiceAccount(GoogleServiceAccountProperties properties) {
        this.properties = properties;
    }

    /** 获取可读取Drive并写入Sheets的短期访问令牌。 */
    public synchronized String accessToken() {
        try {
            GoogleCredentials current = credentials();
            current.refreshIfExpired();
            AccessToken token = current.getAccessToken();
            if (token == null || token.getTokenValue() == null || token.getTokenValue().isBlank())
                throw new DeliveryReportException("Google服务账户未返回访问令牌");
            return token.getTokenValue();
        } catch (IOException | IllegalArgumentException exception) {
            throw new DeliveryReportException("Google服务账户凭据不可用，请检查日报推送配置", exception);
        }
    }

    /** 返回需要被授予Google表格权限的服务账户邮箱。 */
    public synchronized String email() {
        credentials();
        return serviceAccountEmail;
    }

    private GoogleCredentials credentials() {
        if (credentials != null) return credentials;
        try (InputStream input = credentialsInput()) {
            ServiceAccountCredentials loaded = ServiceAccountCredentials.fromStream(input);
            serviceAccountEmail = loaded.getClientEmail();
            credentials = loaded.createScoped(SCOPES);
            return credentials;
        } catch (IOException | IllegalArgumentException exception) {
            throw new DeliveryReportException("Google服务账户凭据不可用，请检查日报推送配置", exception);
        }
    }

    private InputStream credentialsInput() throws IOException {
        if (properties.credentialsBase64() != null
                && !properties.credentialsBase64().isBlank()) {
            return new ByteArrayInputStream(
                    Base64.getDecoder().decode(properties.credentialsBase64().trim()));
        }
        if (properties.credentialsFile() != null && !properties.credentialsFile().isBlank()) {
            return Files.newInputStream(Path.of(properties.credentialsFile().trim()));
        }
        throw new DeliveryReportException(
                "尚未配置Google日报服务账户，请设置凭据文件或Base64凭据");
    }
}
