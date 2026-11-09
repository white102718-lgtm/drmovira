package com.adpulse.main.cloak.client;

import com.adpulse.main.cloak.config.GlobalPwaProperties;
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/** GlobalPWA斗篷服务商HTTP客户端。 */
@Component
public class GlobalPwaClient {
    private static final Logger log = LoggerFactory.getLogger(GlobalPwaClient.class);
    private final GlobalPwaProperties properties;
    private final RestClient client;

    public GlobalPwaClient(GlobalPwaProperties properties) {
        this.properties = properties;
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(properties.getConnectTimeout());
        requestFactory.setReadTimeout(properties.getReadTimeout());
        this.client = RestClient.builder().requestFactory(requestFactory).build();
    }

    /** 查询当前Token可用的斗篷域名。 */
    public List<ProviderDomain> listDomains() {
        properties.validate();
        URI uri = providerUri("domains");
        try {
            DomainEnvelope response =
                    client.get()
                            .uri(uri)
                            .header("X-Api-Token", properties.getApiToken())
                            .retrieve()
                            .body(DomainEnvelope.class);
            if (response == null || response.code() != 200) {
                log.warn("GlobalPWA domain request failed, uri={}, response={}", uri, response);
                throw new GlobalPwaClientException(
                        response == null || blank(response.msg())
                                ? "GlobalPWA域名接口无有效响应"
                                : response.msg());
            }
            log.info("GlobalPWA domain request succeeded, uri={}, response={}", uri, response);
            return response.data() == null ? List.of() : response.data();
        } catch (RestClientException exception) {
            log.error("GlobalPWA domain request error, uri={}", uri, exception);
            throw new GlobalPwaClientException("GlobalPWA域名接口调用失败，请稍后重试", exception);
        }
    }

    /** 查询当前Token可用的投放地区。 */
    public List<ProviderCountry> listCountries() {
        properties.validate();
        URI uri = providerUri("countries");
        try {
            CountryEnvelope response =
                    client.get()
                            .uri(uri)
                            .header("X-Api-Token", properties.getApiToken())
                            .retrieve()
                            .body(CountryEnvelope.class);
            if (response == null || response.code() != 200) {
                log.warn("GlobalPWA country request failed, uri={}, response={}", uri, response);
                throw new GlobalPwaClientException(
                        response == null || blank(response.msg())
                                ? "GlobalPWA地区接口无有效响应"
                                : response.msg());
            }
            log.info("GlobalPWA country request succeeded, uri={}, response={}", uri, response);
            return response.data() == null ? List.of() : response.data();
        } catch (RestClientException exception) {
            log.error("GlobalPWA country request error, uri={}", uri, exception);
            throw new GlobalPwaClientException("GlobalPWA地区接口调用失败，请稍后重试", exception);
        }
    }

    /** 整批创建斗篷；服务商会对数组进行整体校验并保证全成全败。 */
    public String createBatch(List<ProviderCloakCreate> items) {
        properties.validate();
        URI uri = providerUri("batch");
        try {
            ActionEnvelope response =
                    client.post()
                            .uri(uri)
                            .header("X-Api-Token", properties.getApiToken())
                            .body(items)
                            .retrieve()
                            .body(ActionEnvelope.class);
            if (response == null || response.code() != 200) {
                log.warn("GlobalPWA batch create request failed, uri={}, response={}", uri, response);
                throw new GlobalPwaClientException(
                        response == null || blank(response.msg())
                                ? "GlobalPWA批量创建接口无有效响应"
                                : response.msg());
            }
            log.info("GlobalPWA batch create request succeeded, uri={}, response={}", uri, response);
            return response.msg();
        } catch (RestClientException exception) {
            log.error("GlobalPWA batch create request error, uri={}", uri, exception);
            throw new GlobalPwaClientException(
                    "GlobalPWA批量创建接口调用失败，结果需要核对", exception, true);
        }
    }

    /** 按推广链接前缀查询服务商斗篷，用于补齐批量创建响应未返回的主键。 */
    public List<ProviderCloak> listCloaksByAdUrl(String adUrl) {
        properties.validate();
        URI uri =
                UriComponentsBuilder.fromUri(providerUri("list"))
                        .queryParam("pageNum", 1)
                        .queryParam("pageSize", 100)
                        .queryParam("adUrl", adUrl)
                        .build()
                        .encode()
                        .toUri();
        try {
            CloakListEnvelope response =
                    client.get()
                            .uri(uri)
                            .header("X-Api-Token", properties.getApiToken())
                            .retrieve()
                            .body(CloakListEnvelope.class);
            if (response == null || response.code() != 200) {
                log.warn(
                        "GlobalPWA cloak list request failed, uri={}, adUrl={}, response={}",
                        uri,
                        adUrl,
                        response);
                throw new GlobalPwaClientException(
                        response == null || blank(response.msg())
                                ? "GlobalPWA斗篷列表接口无有效响应"
                                : response.msg());
            }
            log.info(
                    "GlobalPWA cloak list request succeeded, uri={}, adUrl={}, response={}",
                    uri,
                    adUrl,
                    response);
            return response.rows() == null ? List.of() : response.rows();
        } catch (RestClientException exception) {
            log.error("GlobalPWA cloak list request error, uri={}, adUrl={}", uri, adUrl, exception);
            throw new GlobalPwaClientException("GlobalPWA斗篷列表接口调用失败，请稍后重试", exception);
        }
    }

    /** 删除指定服务商斗篷；服务商对多个主键执行整批校验。 */
    public void deleteCloaks(List<Long> ids) {
        properties.validate();
        String joinedIds = ids.stream().map(String::valueOf).collect(Collectors.joining(","));
        URI uri = providerUri(joinedIds);
        try {
            ActionEnvelope response =
                    client.delete()
                            .uri(uri)
                            .header("X-Api-Token", properties.getApiToken())
                            .retrieve()
                            .body(ActionEnvelope.class);
            if (response == null || response.code() != 200) {
                log.warn(
                        "GlobalPWA cloak delete request failed, uri={}, ids={}, response={}",
                        uri,
                        joinedIds,
                        response);
                throw new GlobalPwaClientException(
                        response == null || blank(response.msg())
                                ? "GlobalPWA删除斗篷接口无有效响应"
                                : response.msg());
            }
            log.info(
                    "GlobalPWA cloak delete request succeeded, uri={}, ids={}, response={}",
                    uri,
                    joinedIds,
                    response);
        } catch (RestClientException exception) {
            log.error(
                    "GlobalPWA cloak delete request error, uri={}, ids={}",
                    uri,
                    joinedIds,
                    exception);
            throw new GlobalPwaClientException(
                    "GlobalPWA删除斗篷接口调用失败，结果需要核对", exception, true);
        }
    }

    private URI providerUri(String resource) {
        return UriComponentsBuilder.fromUriString(properties.getBaseUrl())
                .pathSegment("open", "cloak", resource)
                .build()
                .toUri();
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    /** 服务商域名下拉响应外层结构。 */
    public record DomainEnvelope(int code, String msg, List<ProviderDomain> data) {}

    /** 服务商返回的单个域名选项。 */
    public record ProviderDomain(String genId, String genDomain, String value, String label) {}

    /** 服务商投放地区下拉响应外层结构。 */
    public record CountryEnvelope(int code, String msg, List<ProviderCountry> data) {}

    /** 服务商返回的单个投放地区选项。 */
    public record ProviderCountry(String country, String value, String label) {}

    /** 服务商通用写操作响应。 */
    public record ActionEnvelope(int code, String msg) {}

    /** 服务商斗篷分页列表响应。 */
    public record CloakListEnvelope(int code, String msg, long total, List<ProviderCloak> rows) {}

    /** 服务商斗篷列表项，仅声明本系统定位删除目标所需字段。 */
    public record ProviderCloak(
            Long id, String reallyUrl, String adUrl, String genId, String genDomain) {}

    /** 服务商批量创建斗篷参数。 */
    public record ProviderCloakCreate(
            String name,
            String reallyUrl,
            String virtualUrl,
            String adUrl,
            String genId,
            String genDomain,
            int type,
            String country,
            int langStatus,
            int pcStatus,
            int vpnStatus) {}

    /** GlobalPWA接口异常，不包含Token或完整响应。 */
    public static class GlobalPwaClientException extends RuntimeException {
        private final boolean uncertain;

        public GlobalPwaClientException(String message) {
            super(message);
            this.uncertain = false;
        }

        public GlobalPwaClientException(String message, Throwable cause) {
            super(message, cause);
            this.uncertain = false;
        }

        public GlobalPwaClientException(
                String message, Throwable cause, boolean uncertain) {
            super(message, cause);
            this.uncertain = uncertain;
        }

        /** 网络异常时无法确认服务商是否已完成创建。 */
        public boolean isUncertain() {
            return uncertain;
        }

        /** 服务商以业务错误返回推广链接重复时，允许上层先查询远端并接管既有结果。 */
        public boolean isDuplicatePromotionUrl() {
            return getMessage() != null && getMessage().contains("推广链接重复");
        }
    }
}
