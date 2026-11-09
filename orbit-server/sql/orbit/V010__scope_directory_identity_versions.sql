-- 目录身份变化同样使权限证明失效；保留V009原触发器，不在迁移中留DROP/CREATE空窗。
CREATE TRIGGER IF NOT EXISTS orbit_sv_account_identity_u AFTER UPDATE ON orbit_account_scope_directory FOR EACH ROW
UPDATE orbit_scope_version SET version=version+1
WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id)
AND (NOT (OLD.id <=> NEW.id) OR NOT (OLD.external_id <=> NEW.external_id));

-- 升级前不能证明旧范围从未经历身份变化，统一失效旧权限版本；重复审核执行也只会递增，不重置。
UPDATE orbit_scope_version SET version=version+1;
