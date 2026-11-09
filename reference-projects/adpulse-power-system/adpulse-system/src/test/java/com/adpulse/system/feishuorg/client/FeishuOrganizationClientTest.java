package com.adpulse.system.feishuorg.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.adpulse.system.feishuorg.mapper.FeishuOrganizationMapper;
import com.adpulse.system.feishuorg.model.FeishuApplicationConfig;
import com.adpulse.system.feishuorg.model.FeishuOrganizationSnapshot;
import com.adpulse.system.feishuorg.security.FeishuSecretCipher;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/** 飞书企业根部门和组织快照读取测试。 */
class FeishuOrganizationClientTest {

    @ParameterizedTest
    @ValueSource(
            strings = {
                "{\"code\":0}",
                "{\"code\":0,\"data\":{\"items\":[],\"has_more\":true}}",
                "{\"code\":0,\"data\":{\"items\":{}}}",
                "{\"code\":0,\"data\":{\"items\":[null],\"has_more\":false}}"
            })
    void rejectsIncompletePagesInsteadOfTreatingThemAsFullSnapshots(String response) {
        var fixture = fixture();
        fixture.server()
                .expect(requestTo(containsString("/departments/0/children")))
                .andRespond(withSuccess(response, MediaType.APPLICATION_JSON));
        assertThatThrownBy(() -> fixture.client().fetchSnapshot()).hasMessageContaining("飞书");
        fixture.server().verify();
    }

    @Test
    void rejectsRepeatedPageToken() {
        var fixture = fixture();
        String page =
                "{\"code\":0,\"data\":{\"items\":[],\"has_more\":true,\"page_token\":\"same\"}}";
        fixture.server()
                .expect(requestTo(containsString("/departments/0/children")))
                .andRespond(withSuccess(page, MediaType.APPLICATION_JSON));
        fixture.server()
                .expect(requestTo(containsString("page_token=same")))
                .andRespond(withSuccess(page, MediaType.APPLICATION_JSON));
        assertThatThrownBy(() -> fixture.client().fetchSnapshot()).hasMessageContaining("分页标识");
        fixture.server().verify();
    }

    @Test
    void rejectsMissingUserStatusRatherThanDisablingEveryone() {
        var fixture = fixture();
        fixture.server()
                .expect(requestTo(containsString("/departments/0/children")))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"data\":{\"items\":[],\"has_more\":false}}",
                                MediaType.APPLICATION_JSON));
        fixture.server()
                .expect(requestTo(containsString("/users/find_by_department")))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"data\":{\"items\":[{\"user_id\":\"u1\"}],\"has_more\":false}}",
                                MediaType.APPLICATION_JSON));
        assertThatThrownBy(() -> fixture.client().fetchSnapshot()).hasMessageContaining("人员状态缺失");
        fixture.server().verify();
    }

    private Fixture fixture() {
        var mapper = mock(FeishuOrganizationMapper.class);
        var cipher = mock(FeishuSecretCipher.class);
        var config = new FeishuApplicationConfig();
        config.setAppId("app");
        config.setAppSecretCiphertext("cipher");
        when(mapper.findApplicationConfig()).thenReturn(config);
        when(cipher.decrypt("cipher")).thenReturn("test-secret");
        var builder = RestClient.builder();
        var server = MockRestServiceServer.bindTo(builder).build();
        var client = new FeishuOrganizationClient(mapper, cipher, builder);
        server.expect(requestTo(containsString("/tenant_access_token/internal")))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"tenant_access_token\":\"test-token\"}",
                                MediaType.APPLICATION_JSON));
        server.expect(requestTo(containsString("/tenant/v2/tenant/query")))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"data\":{\"tenant\":{\"tenant_key\":\"tenant\",\"name\":\"公司\"}}}",
                                MediaType.APPLICATION_JSON));
        return new Fixture(server, client);
    }

    private record Fixture(MockRestServiceServer server, FeishuOrganizationClient client) {}

    @Test
    void resolvesOpenIdByMobileForTestNotificationFallback() {
        FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
        FeishuSecretCipher cipher = mock(FeishuSecretCipher.class);
        FeishuApplicationConfig config = new FeishuApplicationConfig();
        config.setAppId("cli_test");
        config.setAppSecretCiphertext("ciphertext");
        when(mapper.findApplicationConfig()).thenReturn(config);
        when(cipher.decrypt("ciphertext")).thenReturn("app-secret");

        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        FeishuOrganizationClient client = new FeishuOrganizationClient(mapper, cipher, builder);
        server.expect(requestTo(containsString("/auth/v3/tenant_access_token/internal")))
                .andExpect(method(HttpMethod.POST))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"tenant_access_token\":\"tenant-token\"}",
                                MediaType.APPLICATION_JSON));
        server.expect(requestTo(containsString("/contact/v3/users/batch_get_id")))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Authorization", "Bearer tenant-token"))
                .andRespond(
                        withSuccess(
                                "{\"code\":0,\"data\":{\"user_list\":[{\"user_id\":\"open-test\"}]}}",
                                MediaType.APPLICATION_JSON));

        assertThat(client.findOpenIdsByMobile("15362469449")).containsExactly("open-test");
        server.verify();
    }

    @Test
    void shouldCreateTenantRootAndReparentTopLevelDepartmentsAndUsers() {
        FeishuOrganizationMapper mapper = mock(FeishuOrganizationMapper.class);
        FeishuSecretCipher cipher = mock(FeishuSecretCipher.class);
        FeishuApplicationConfig config = new FeishuApplicationConfig();
        config.setAppId("cli_test");
        config.setAppSecretCiphertext("ciphertext");
        when(mapper.findApplicationConfig()).thenReturn(config);
        when(cipher.decrypt("ciphertext")).thenReturn("app-secret");

        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        FeishuOrganizationClient client = new FeishuOrganizationClient(mapper, cipher, builder);

        server.expect(requestTo(containsString("/auth/v3/tenant_access_token/internal")))
                .andExpect(method(HttpMethod.POST))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"tenant_access_token":"REDACTED_REFERENCE_SECRET"}
                                """,
                                MediaType.APPLICATION_JSON));
        server.expect(requestTo(containsString("/tenant/v2/tenant/query")))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("Authorization", "Bearer tenant-token"))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"data":{"tenant":{"tenant_key":"tenant-1","name":"示例公司"}}}
                                """,
                                MediaType.APPLICATION_JSON));
        server.expect(requestTo(containsString("/contact/v3/departments/0/children")))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"data":{"items":[{"department_id":"od-1","parent_department_id":"0","name":"研发部","order":"10","leaders":[]}],"has_more":false}}
                                """,
                                MediaType.APPLICATION_JSON));
        server.expect(
                        requestTo(
                                containsString(
                                        "/contact/v3/users/find_by_department?department_id=0")))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"data":{"items":[{"user_id":"u-root","open_id":"ou-root","union_id":"on-root","name":"直属员工","department_ids":["0"],"status":{"is_activated":true}}],"has_more":false}}
                                """,
                                MediaType.APPLICATION_JSON));
        server.expect(
                        requestTo(
                                containsString(
                                        "/contact/v3/users/find_by_department?department_id=od-1")))
                .andRespond(
                        withSuccess(
                                """
                                {"code":0,"data":{"items":[{"user_id":"u-dev","open_id":"ou-dev","union_id":"on-dev","name":"研发员工","department_ids":["od-1"],"status":{"is_activated":true}}],"has_more":false}}
                                """,
                                MediaType.APPLICATION_JSON));

        FeishuOrganizationSnapshot snapshot = client.fetchSnapshot();

        assertThat(snapshot.tenantKey()).isEqualTo("tenant-1");
        assertThat(snapshot.departments()).hasSize(2);
        assertThat(snapshot.departments().getFirst().departmentId())
                .isEqualTo(FeishuOrganizationClient.TENANT_ROOT_EXTERNAL_ID);
        assertThat(snapshot.departments().getFirst().name()).isEqualTo("示例公司");
        assertThat(snapshot.departments().get(1).parentDepartmentId())
                .isEqualTo(FeishuOrganizationClient.TENANT_ROOT_EXTERNAL_ID);
        assertThat(snapshot.users())
                .filteredOn(user -> user.userId().equals("u-root"))
                .singleElement()
                .extracting(user -> user.departmentIds().getFirst())
                .isEqualTo(FeishuOrganizationClient.TENANT_ROOT_EXTERNAL_ID);
        server.verify();
    }
}
