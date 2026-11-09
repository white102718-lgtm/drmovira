package com.adpulse.main.project.model;

/** 未软删除的人员引用；停用状态只用于历史归属校验，不授予登录权限。 */
public record ProjectUserReference(Long id, String displayName, Integer status) {}
