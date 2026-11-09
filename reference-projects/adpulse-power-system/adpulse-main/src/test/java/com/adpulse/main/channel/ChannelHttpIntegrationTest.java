package com.adpulse.main.channel;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.adpulse.system.common.security.CurrentUser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/** 使用真实 Controller、Service、MyBatis 和测试数据库验证渠道 HTTP 全链路。 */
@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "RUN_CHANNEL_HTTP_IT", matches = "true")
class ChannelHttpIntegrationTest {
    @Autowired private MockMvc mockMvc;
    @Autowired private ObjectMapper objectMapper;

    @Test
    void shouldExerciseChannelDetailAndAssociatedAccountOperations() throws Exception {
        String accountId = "E2E" + System.currentTimeMillis();
        boolean accountCreated = false;

        JsonNode channels = getJson("/channels?page=1&pageSize=10&status=1");
        assertSuccess(channels);
        assertThat(channels.path("data").path("items").size()).isGreaterThanOrEqualTo(4);
        String channelId = channels.path("data").path("items").get(0).path("id").asText();

        JsonNode detail = getJson("/channels/" + channelId);
        assertSuccess(detail);
        assertThat(detail.path("data").path("channelName").asText()).isNotBlank();
        assertSuccess(getJson("/channels/" + channelId + "/rates?page=1&pageSize=20"));
        assertSuccess(getJson("/channels/" + channelId + "/goods"));
        assertSuccess(getJson("/channels/" + channelId + "/account-counts"));

        try {
            assertSuccess(
                    performJson(
                            post("/channels/" + channelId + "/accounts/batch"),
                            "{\"channelId\":"
                                    + channelId
                                    + ",\"accounts\":[{\"accountId\":\""
                                    + accountId
                                    + "\",\"accountType\":\"企业户\"}]}"));
            accountCreated = true;

            JsonNode accounts =
                    performJson(
                            post("/channel-accounts/search"),
                            "{\"channelId\":"
                                    + channelId
                                    + ",\"accountIds\":[\""
                                    + accountId
                                    + "\"],\"startDate\":\"2026-08-01\","
                                    + "\"endDate\":\"2026-08-24\",\"page\":1,\"pageSize\":10}");
            assertSuccess(accounts);
            assertThat(accounts.path("data").path("items")).hasSize(1);

            JsonNode pitchers = getJson("/channel-support/pitchers?page=1&pageSize=10");
            assertSuccess(pitchers);
            if (!pitchers.path("data").path("items").isEmpty()) {
                String operatorId =
                        pitchers.path("data").path("items").get(0).path("userId").asText();
                assertSuccess(
                        performJson(
                                patch("/channel-accounts/assignment"),
                                "{\"accountIds\":[\""
                                        + accountId
                                        + "\"],\"operatorId\":"
                                        + operatorId
                                        + "}"));
            }

            JsonNode campaigns =
                    getJson("/channel-accounts/790000000001001/campaigns?page=1&pageSize=10");
            assertSuccess(campaigns);
            assertThat(campaigns.path("data").path("items").size()).isGreaterThanOrEqualTo(3);
        } finally {
            if (accountCreated) {
                assertSuccess(
                        read(
                                mockMvc.perform(
                                                delete("/channel-accounts/" + accountId)
                                                        .with(auth()))
                                        .andExpect(status().isOk())
                                        .andReturn()
                                        .getResponse()
                                        .getContentAsString()));
            }
        }
    }

    private JsonNode getJson(String path) throws Exception {
        return read(
                mockMvc.perform(get(path).with(auth()))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsString());
    }

    private JsonNode performJson(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder builder,
            String body)
            throws Exception {
        return read(
                mockMvc.perform(
                                builder.with(auth())
                                        .contentType(MediaType.APPLICATION_JSON)
                                        .content(body))
                        .andExpect(status().isOk())
                        .andReturn()
                        .getResponse()
                        .getContentAsString());
    }

    private RequestPostProcessor auth() {
        CurrentUser user = new CurrentUser(1L, "channel-http-it", "渠道接口测试", List.of());
        return authentication(new UsernamePasswordAuthenticationToken(user, null, List.of()));
    }

    private JsonNode read(String content) throws Exception {
        return objectMapper.readTree(content);
    }

    private void assertSuccess(JsonNode response) {
        assertThat(response.path("code").asInt()).as(response.toString()).isEqualTo(200);
    }
}
