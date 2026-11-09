package com.adpulse.main.home;

import com.adpulse.system.common.api.ApiResponse;
import com.adpulse.system.common.security.CurrentUser;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 主业务服务基础接口。 */
@RestController
@RequestMapping("/home")
public class MainController {

    /** 返回当前通过共享会话认证的用户摘要。 */
    @GetMapping
    public ApiResponse<Map<String, Object>> home(@AuthenticationPrincipal CurrentUser currentUser) {
        return ApiResponse.success(
                Map.of(
                        "userId",
                        currentUser.userId().toString(),
                        "displayName",
                        currentUser.displayName()));
    }
}
