package com.ruoyi.web.controller.orbit;

import com.fasterxml.jackson.databind.JsonNode;
import com.ruoyi.system.orbit.config.ConfigurationException;
import com.ruoyi.system.orbit.config.ConfigurationModels.View;
import com.ruoyi.system.orbit.config.ConfigurationService;
import java.util.List;
import java.util.Map;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

/** ORBIT系统配置入口；不用默认@Log记录含密钥的请求体，审计由服务层脱敏保存。 */
@RestController
@RequestMapping("/api/v1/system-configurations")
@PreAuthorize("@ss.hasPermi('system.read') and @ss.hasPermi('system.integrations.manage')")
public class OrbitConfigurationController {
    private final ConfigurationService service;

    public OrbitConfigurationController(ConfigurationService service) {
        this.service = service;
    }

    @GetMapping("/metadata")
    public Map<String, Object> metadata() {
        return service.metadata();
    }

    @GetMapping
    public List<View> list() {
        return service.list();
    }

    @GetMapping("/{id}")
    public View get(@PathVariable String id) {
        return service.get(id);
    }

    @GetMapping("/{id}/history")
    public com.ruoyi.system.orbit.config.ConfigurationModels.AuditPage history(
            @PathVariable String id,
            @RequestParam(required = false) Long beforeRevision,
            @RequestParam(defaultValue = "50") int pageSize) {
        return service.history(id, beforeRevision, pageSize);
    }

    @PostMapping
    @ResponseStatus(org.springframework.http.HttpStatus.CREATED)
    public View create(
            @RequestHeader("Idempotency-Key") String requestKey, @RequestBody JsonNode body) {
        return service.save(null, 0, requestKey, service.parse(body));
    }

    @PutMapping("/{id}")
    public View update(
            @PathVariable String id,
            @RequestHeader("If-Match") String revision,
            @RequestHeader("Idempotency-Key") String requestKey,
            @RequestBody JsonNode body) {
        return service.save(id, revision(revision), requestKey, service.parse(body));
    }

    @PostMapping("/{id}/test")
    public Map<String, Object> test(
            @PathVariable String id,
            @RequestHeader("If-Match") String revision,
            @RequestBody JsonNode body) {
        return service.test(id, revision(revision), service.parseTestReason(body));
    }

    private static long revision(String value) {
        if (!value.matches("\"[1-9][0-9]{0,17}\"")) {
            throw new ConfigurationException(400, "REVISION_REQUIRED", "If-Match必须为带引号的正整数版本");
        }
        return Long.parseLong(value.substring(1, value.length() - 1));
    }
}
