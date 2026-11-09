package com.adpulse.system.auth.security;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Component;

/** 解析请求来源IP；仅在可信反向代理覆盖头信息时启用转发头。 */
@Component
public class ClientIpResolver {

    /** 返回 Servlet 容器确认的远端地址。 */
    public String resolve(HttpServletRequest request) {
        return request.getRemoteAddr();
    }
}
