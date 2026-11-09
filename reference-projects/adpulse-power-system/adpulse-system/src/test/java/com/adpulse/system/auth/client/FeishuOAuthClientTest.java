package com.adpulse.system.auth.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.adpulse.system.auth.model.FeishuIdentity;
import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** 飞书 OAuth 授权码交换与身份解析测试。 */
class FeishuOAuthClientTest {

    @Test
    void shouldExchangeAuthorizationCodeWithoutPersistingUserToken() {
        FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
        FeishuSecretCipher cipher = mock(FeishuSecretCipher.class);
        FeishuApplicationConfig config = new FeishuApplicationConfig();
        config.setAppId("cli_test");
        config.setAppSecretCiphertext("ciphertext");
        when(mapper.findApplicationConfig()).thenReturn(config);
        when(cipher.decrypt("ciphertext")).thenReturn("app-secret");

        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        FeishuOAuthClient client = new FeishuOAuthClient(mapper, cipher, builder);

        server.expect(requestTo(containsString("/auth/v3/app_access_token/internal")))
                .andExpect(method(HttpMethod.POST))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"app_access_token":"REDACTED_REFERENCE_SECRET"}
                                """,
                                MediaType.APPLICATION_JSON));
        server.expect(requestTo(containsString("/authen/v1/access_token")))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Authorization", "Bearer app-token"))
                .andRespond(
                        withSuccess(
                                """
                                {
                                  "code":0,
                                  "data":{
                                    "access_token":"REDACTED_REFERENCE_SECRET",
                                    "tenant_key":"tenant-1",
                                    "open_id":"ou_1",
                                    "union_id":"on_1",
                                    "name":"飞书用户"
                                  }
                                }
                                """,
                                MediaType.APPLICATION_JSON));

        FeishuIdentity identity = client.exchangeCode("one-time-code");

        assertThat(identity).isEqualTo(new FeishuIdentity("tenant-1", "ou_1", "on_1", "飞书用户"));
        server.verify();
    }
}
