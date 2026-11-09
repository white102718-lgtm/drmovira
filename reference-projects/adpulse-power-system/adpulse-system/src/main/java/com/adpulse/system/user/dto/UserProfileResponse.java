package com.adpulse.system.user.dto;

import java.util.List;

/** 当前登录用户的个人资料。 */
public record UserProfileResponse(
        String userId,
        String username,
        String phone,
        String displayName,
        String englishNickname,
        String realName,
        String email,
        String avatarUrl,
        String department,
        List<String> departments,
        List<String> roles,
        boolean hasPassword) {}
