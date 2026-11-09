-- 模板历史的精确指标依赖；历史NULL保留未知，不伪造已核验的空对象。
ALTER TABLE orbit_launch_template
 ADD COLUMN dependency_json JSON NULL COMMENT '当前模板的服务端精确指标依赖；历史NULL为尚无来源快照' AFTER config_bytes,
 ADD CONSTRAINT chk_template_dependency_object CHECK(dependency_json IS NULL OR JSON_TYPE(dependency_json)='OBJECT');
ALTER TABLE orbit_launch_template_version
 ADD COLUMN dependency_json JSON NULL COMMENT '本版本冻结的指标版本摘要和来源配置版本；历史NULL不回填' AFTER value_json,
 ADD CONSTRAINT chk_template_version_dependency_object CHECK(dependency_json IS NULL OR JSON_TYPE(dependency_json)='OBJECT');
CREATE TRIGGER launch_template_version_update_guard BEFORE UPDATE ON orbit_launch_template_version
FOR EACH ROW BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEMPLATE_VERSION_IMMUTABLE';
END;
CREATE TRIGGER launch_template_version_delete_guard BEFORE DELETE ON orbit_launch_template_version
FOR EACH ROW BEGIN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEMPLATE_VERSION_IMMUTABLE';
END;
