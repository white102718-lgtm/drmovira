-- 主线041：显式升级指标配置分页来源水位与目录入口。
-- 新租户必须由目录初始化流程准备所有业务clock，不能在触发器中悄悄伪造分页水位。
CREATE TRIGGER metric_configuration_insert AFTER INSERT ON orbit_system_configuration
FOR EACH ROW BEGIN
 IF NEW.section='META_BM' THEN
  UPDATE orbit_metric_profile_clock SET revision=revision+1
   WHERE tenant_id=NEW.tenant_id AND revision<9007199254740991;
  IF ROW_COUNT()<>1 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_UNAVAILABLE';
  END IF;
 END IF;
END;

CREATE TRIGGER metric_configuration_delete AFTER DELETE ON orbit_system_configuration
FOR EACH ROW BEGIN
 IF OLD.section='META_BM' THEN
  UPDATE orbit_metric_profile_clock SET revision=revision+1
   WHERE tenant_id=OLD.tenant_id AND revision<9007199254740991;
  IF ROW_COUNT()<>1 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_UNAVAILABLE';
  END IF;
 END IF;
END;

CREATE TRIGGER metric_configuration_update AFTER UPDATE ON orbit_system_configuration
FOR EACH ROW BEGIN
 IF OLD.section='META_BM' AND NEW.section='META_BM' AND OLD.tenant_id<>NEW.tenant_id THEN
  UPDATE orbit_metric_profile_clock SET revision=revision+1
   WHERE tenant_id IN (OLD.tenant_id,NEW.tenant_id) AND revision<9007199254740991
   ORDER BY tenant_id;
  IF ROW_COUNT()<>2 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_UNAVAILABLE';
  END IF;
 ELSEIF OLD.section='META_BM' THEN
  UPDATE orbit_metric_profile_clock SET revision=revision+1
   WHERE tenant_id=OLD.tenant_id AND revision<9007199254740991;
  IF ROW_COUNT()<>1 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_UNAVAILABLE';
  END IF;
 ELSEIF NEW.section='META_BM' THEN
  UPDATE orbit_metric_profile_clock SET revision=revision+1
   WHERE tenant_id=NEW.tenant_id AND revision<9007199254740991;
  IF ROW_COUNT()<>1 THEN
   SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_UNAVAILABLE';
  END IF;
 END IF;
END;
