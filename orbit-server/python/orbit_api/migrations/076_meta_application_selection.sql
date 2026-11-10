-- 后台应用来源与原生登录的安全浏览器会话；不迁移已有凭据到其他来源。
ALTER TABLE orbit_browser_session
 MODIFY provider_id CHAR(36) NULL COMMENT 'OIDC配置UUID；原生已验证登录会话为NULL',
 MODIFY provider_revision BIGINT NULL COMMENT 'OIDC配置版本；原生会话为NULL',
 ADD COLUMN authentication_kind VARCHAR(16) NOT NULL DEFAULT 'OIDC' COMMENT 'OIDC或NATIVE：服务端验证的认证来源',
 ADD CONSTRAINT ck_browser_auth_kind CHECK ((authentication_kind='OIDC' AND provider_id IS NOT NULL AND provider_revision IS NOT NULL) OR (authentication_kind='NATIVE' AND provider_id IS NULL AND provider_revision IS NULL));
ALTER TABLE orbit_meta_authorization_session
 ADD COLUMN app_configuration_id CHAR(36) NULL COMMENT '所选本租户Meta应用配置UUID；NULL为历史受控服务端应用',
 ADD COLUMN app_configuration_revision BIGINT NULL COMMENT '发起授权时应用配置版本；变更后回调拒绝';
ALTER TABLE orbit_meta_connection
 ADD COLUMN app_configuration_id CHAR(36) NULL COMMENT '读取凭据绑定的Meta应用配置UUID',
 ADD COLUMN app_configuration_revision BIGINT NULL COMMENT '授权完成时应用配置版本；变化后重新授权';
