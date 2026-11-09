package com.adpulse.system.auth.dto;

/** 飞书二维码 SDK 初始化参数。 */
public record FeishuQrInitResponse(String gotoUrl, long expiresInSeconds) {}
