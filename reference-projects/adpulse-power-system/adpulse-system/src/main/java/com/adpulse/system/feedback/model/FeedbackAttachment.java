package com.adpulse.system.feedback.model;

/** 反馈附件查询快照。 */
public record FeedbackAttachment(
        Long id, String originalName, String mimeType, Long fileSize, Integer sortOrder) {}
