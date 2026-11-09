package com.adpulse.main.project.wallet.mpower;

import com.adpulse.main.project.wallet.ProjectWalletProvider.ProjectWalletContext;
import com.adpulse.main.project.wallet.ProjectWalletProvider.UserReference;
import com.adpulse.main.project.wallet.mpower.LegacyMpowerMappingMapper.LegacyDepartment;
import com.adpulse.main.project.wallet.mpower.LegacyMpowerMappingMapper.LegacyUser;
import com.adpulse.main.project.wallet.mpower.LegacyMpowerMappingReader.MappingCandidates;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/** 以老库为真实来源解析项目字段，Redis只缓存已校验的解析结果。 */
@Component
public class LegacyMpowerFieldMappingResolver {
    private static final String KEY_PREFIX = "adpulse:mpower-wallet:field-map:v1:";
    private final LegacyMpowerMappingReader reader;
    private final MpowerWalletProperties properties;
    private final ObjectMapper json;
    private final StringRedisTemplate redis;

    public LegacyMpowerFieldMappingResolver(
            LegacyMpowerMappingReader reader,
            MpowerWalletProperties properties,
            ObjectMapper json,
            ObjectProvider<StringRedisTemplate> redis) {
        this.reader = reader;
        this.properties = properties;
        this.json = json;
        this.redis = redis.getIfAvailable();
    }

    /** 优先读取缓存；未命中或缓存不可用时查询老库并回写有期限缓存。 */
    public LegacyProjectFields resolve(ProjectWalletContext context) {
        MappingInput input = input(context);
        String key = cacheKey(input);
        LegacyProjectFields cached = cached(key);
        if (cached != null) return cached;

        MappingCandidates candidates =
                reader.read(
                        properties.getDefaultTenantId(),
                        input.responsibleTeam(),
                        input.userNames());
        Resolution department = resolveDepartment(input.responsibleTeam(), candidates.departments());
        Resolution am = resolveUsers(input.amNames(), candidates.users());
        Resolution specialist = resolveUsers(input.specialistNames(), candidates.users());
        String region =
                input.regionNames().stream()
                        .filter(value -> !blank(value))
                        .findFirst()
                        .orElse(properties.getDefaultRegion());
        boolean fallbackUsed =
                department.fallbackUsed()
                        || am.fallbackUsed()
                        || specialist.fallbackUsed()
                        || input.regionNames().isEmpty();
        LegacyProjectFields fields =
                new LegacyProjectFields(
                        department.value(), region, am.value(), specialist.value(), fallbackUsed);
        cache(
                key,
                fields,
                fallbackUsed
                        ? properties.getMappingFallbackCacheTtl()
                        : properties.getMappingCacheTtl());
        return fields;
    }

    private MappingInput input(ProjectWalletContext context) {
        List<String> amNames = userNames(context.amUsers());
        List<String> specialistNames = userNames(context.dataSpecialists());
        Set<String> allUsers = new LinkedHashSet<>(amNames);
        allUsers.addAll(specialistNames);
        return new MappingInput(
                normalize(properties.getSourceUuid()),
                normalize(properties.getSourceSchema()),
                properties.getDefaultTenantId(),
                normalize(context.responsibleTeam()),
                normalized(context.countryRegions()),
                amNames,
                specialistNames,
                List.copyOf(allUsers));
    }

    private Resolution resolveDepartment(String name, List<LegacyDepartment> candidates) {
        List<String> ids =
                candidates.stream()
                        .filter(item -> name.equals(normalize(item.departmentName())))
                        .map(LegacyDepartment::departmentId)
                        .filter(value -> !blank(value))
                        .distinct()
                        .toList();
        return ids.size() == 1
                ? new Resolution(ids.getFirst(), false)
                : new Resolution(properties.getDefaultDepartmentId(), true);
    }

    private Resolution resolveUsers(List<String> names, List<LegacyUser> candidates) {
        Set<String> ids = new LinkedHashSet<>();
        for (String name : names) {
            List<String> matched =
                    candidates.stream()
                            .filter(
                                    user ->
                                            name.equals(normalize(user.nickName()))
                                                    || name.equals(normalize(user.userName())))
                            .map(LegacyUser::userId)
                            .filter(value -> !blank(value))
                            .distinct()
                            .toList();
            if (matched.size() == 1) ids.add(matched.getFirst());
        }
        return ids.isEmpty()
                ? new Resolution(properties.getDefaultUserId(), true)
                : new Resolution(String.join(",", ids), ids.size() < names.size());
    }

    private List<String> userNames(List<UserReference> users) {
        if (users == null) return List.of();
        return users.stream()
                .map(UserReference::userName)
                .map(this::normalize)
                .filter(value -> !blank(value))
                .distinct()
                .toList();
    }

    private List<String> normalized(List<String> values) {
        if (values == null) return List.of();
        return values.stream()
                .map(this::normalize)
                .filter(value -> !blank(value))
                .distinct()
                .toList();
    }

    private LegacyProjectFields cached(String key) {
        if (!properties.isMappingCacheEnabled() || redis == null) return null;
        try {
            String value = redis.opsForValue().get(key);
            if (blank(value)) return null;
            LegacyProjectFields fields = json.readValue(value, LegacyProjectFields.class);
            return fields.valid() ? fields : null;
        } catch (RuntimeException | JsonProcessingException exception) {
            return null;
        }
    }

    private void cache(String key, LegacyProjectFields fields, Duration ttl) {
        if (!properties.isMappingCacheEnabled() || redis == null || ttl == null || ttl.isZero()) {
            return;
        }
        try {
            redis.opsForValue().set(key, json.writeValueAsString(fields), ttl);
        } catch (RuntimeException | JsonProcessingException ignored) {
            // Redis只是可丢弃缓存，不影响老库回源。
        }
    }

    private String cacheKey(MappingInput input) {
        try {
            String payload = json.writeValueAsString(input);
            return KEY_PREFIX
                    + normalize(properties.getMappingNamespace()).toUpperCase(Locale.ROOT)
                    + ":"
                    + sha256(payload);
        } catch (JsonProcessingException exception) {
            throw new MpowerWalletClient.MpowerWalletClientException("旧MPower映射缓存键生成失败", exception);
        }
    }

    private String sha256(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private record MappingInput(
            String sourceUuid,
            String sourceSchema,
            Integer tenantId,
            String responsibleTeam,
            List<String> regionNames,
            List<String> amNames,
            List<String> specialistNames,
            List<String> userNames) {}

    private record Resolution(String value, boolean fallbackUsed) {}

    /** 调用旧系统创建项目所需的已解析字段。 */
    public record LegacyProjectFields(
            String liabilityCompany,
            String region,
            String am,
            String dataSpecialist,
            boolean fallbackUsed) {
        private boolean valid() {
            return liabilityCompany != null
                    && !liabilityCompany.isBlank()
                    && region != null
                    && !region.isBlank()
                    && am != null
                    && !am.isBlank()
                    && dataSpecialist != null
                    && !dataSpecialist.isBlank();
        }
    }
}
