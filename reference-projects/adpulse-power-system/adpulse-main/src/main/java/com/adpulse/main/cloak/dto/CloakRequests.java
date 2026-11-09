package com.adpulse.main.cloak.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 斗篷管理请求模型。 */
public final class CloakRequests {
    private CloakRequests() {}

    /** 批量创建斗篷请求；真实链接由后端根据项目代理线读取。 */
    public record BatchCreate(
            @NotBlank @Size(max = 64) String requestId,
            @NotBlank String projectId,
            @NotBlank @Size(max = 1000) String reviewUrl,
            @NotNull @Pattern(regexp = "off|all|cloak") String mode,
            @Size(max = 500) String country,
            @Size(max = 255) String countryLabel,
            boolean blockedLanguage,
            boolean blockedPc,
            boolean blockedProxy,
            @NotEmpty @Size(max = 100) List<@Valid BatchItem> items) {}

    /** 单条斗篷创建参数，只接受稳定代理线ID和服务商域名标识。 */
    public record BatchItem(
            @NotBlank String agencyLineId,
            @NotBlank(message = "不能为空")
                    @Size(max = 100, message = "不能超过100个字符")
                    @Pattern(
                            regexp = "[A-Za-z0-9]*",
                            message =
                                    "格式不正确：服务商仅支持大小写英文字母和数字，请勿填写点号、连字符或 http://、https://")
                    String adUrl,
            @NotBlank @Size(max = 100) String genId,
            @NotBlank @Size(max = 255) String genDomain) {}

    /** 斗篷管理列表按本地记录主键发起Google Sheet回填。 */
    public record SheetWriteback(
            @NotEmpty @Size(max = 100) List<@NotBlank String> recordIds) {}
}
