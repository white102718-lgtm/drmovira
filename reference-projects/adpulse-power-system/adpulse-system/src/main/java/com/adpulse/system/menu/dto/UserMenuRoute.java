package com.adpulse.system.menu.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 登录用户可访问的前端动态路由节点。 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record UserMenuRoute(
        @JsonProperty("_id") String id,
        String pid,
        String name,
        String path,
        String component,
        String authCode,
        String type,
        Meta meta,
        List<UserMenuRoute> children) {

    /** Vben动态路由使用的菜单元数据。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record Meta(
            String title,
            String icon,
            Integer order,
            boolean hideInMenu,
            boolean keepAlive,
            String link) {}
}
