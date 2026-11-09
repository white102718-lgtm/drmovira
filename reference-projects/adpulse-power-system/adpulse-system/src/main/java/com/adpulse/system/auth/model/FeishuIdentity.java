package com.adpulse.system.auth.model;

/** 飞书授权码换取的用户身份，不保存用户访问令牌。 */
public record FeishuIdentity(String tenantKey, String openId, String unionId, String displayName) {}
