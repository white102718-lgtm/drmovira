-- 072：生产读取采集检查点及独立覆盖清单；数值事实继续使用048，默认不启动调度。
CREATE TABLE orbit_meta_metric_job (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '采集检查点UUID',
 publication_id CHAR(36) NOT NULL COMMENT '预分配原048发行UUID，完整发布前不可查询',
 account_id CHAR(36) NOT NULL COMMENT '固定原业务账户UUID',
 connection_id CHAR(36) NOT NULL COMMENT '真实OAuth或BM连接UUID，不伪装系统配置',
 connection_revision BIGINT NOT NULL COMMENT '冻结真实连接版本',
 account_source_revision BIGINT NOT NULL COMMENT '冻结账户来源关联版本',
 actor_id BIGINT NOT NULL COMMENT '实际发起读取的原生用户ID',
 profile_id CHAR(36) NOT NULL COMMENT '既有验证归因配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '冻结归因配置字符串版本',
 profile_hash CHAR(64) NOT NULL COMMENT '原归因配置完整摘要',
 adapter_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '已验证归因映射适配版本',
 api_version VARCHAR(16) NOT NULL COMMENT '固定Graph版本，不使用latest',
 source_fingerprint CHAR(64) NOT NULL COMMENT '连接UUID版本及API版本规范摘要，不含密钥',
 date_from DATE NOT NULL COMMENT '账户当地业务日开始',
 date_to DATE NOT NULL COMMENT '账户当地业务日结束，最长93日',
 capture_sequence BIGINT NOT NULL COMMENT '网络采集开始前分配的单调序号',
 state VARCHAR(16) NOT NULL COMMENT 'INVENTORY/CAPTURING/SEALED/PUBLISHED/RETRY_WAIT/WAIT_REPORT/FAILED',
 attempts INT NOT NULL DEFAULT 0 COMMENT '实际执行尝试次数，报表等候不增加，最多三次',
 lease_owner CHAR(36) NULL COMMENT '当前内部Worker实例UUID',
 fencing_token BIGINT NOT NULL DEFAULT 0 COMMENT '每次领取单调递增代际',
 lease_expires_at DATETIME(6) NULL COMMENT '领取租约UTC截止，失效停止发布',
 next_run_at DATETIME(6) NOT NULL COMMENT '重试或首次领取最早UTC',
 report_id VARCHAR(64) NULL COMMENT '平台异步只读报告ID，无Token',
 after_cursor TEXT NULL COMMENT '受控API游标，不保存含Token的next URL',
 page_number INT NOT NULL DEFAULT 0 COMMENT '已原子持久页数',
 checkpoint_json JSON NOT NULL COMMENT '受控分页/重试检查点，无密钥或完整URL',
 request_hash CHAR(64) NOT NULL COMMENT '冻结采集业务意图摘要',
 inventory_hash CHAR(64) NULL COMMENT '独立库存封存根；不能从指标返回行反推',
 expected_unit_count BIGINT NOT NULL DEFAULT 0 COMMENT '独立账户日期层级单元总数',
 expected_member_count BIGINT NOT NULL DEFAULT 0 COMMENT '独立库存实体日期成员总数',
 created_at DATETIME(6) NOT NULL COMMENT '真实创建UTC',
 updated_at DATETIME(6) NOT NULL COMMENT '最后实际推进UTC',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_meta_metric_job_publication(tenant_id,publication_id),
 UNIQUE KEY uq_meta_metric_job_intent(tenant_id,actor_id,request_hash),
 KEY ix_meta_metric_job_due(state,next_run_at,tenant_id,id),
 KEY ix_meta_metric_job_account(tenant_id,account_id,created_at,id),
 KEY ix_meta_metric_job_account_state(tenant_id,account_id,state,updated_at),
 FOREIGN KEY(tenant_id,connection_id) REFERENCES orbit_meta_connection(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 FOREIGN KEY(tenant_id,profile_id,profile_version,profile_hash)
 REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 CHECK(attempts BETWEEN 0 AND 3),
 CHECK(fencing_token BETWEEN 0 AND 9007199254740991),
 CHECK(capture_sequence BETWEEN 1 AND 9007199254740991),
 CHECK(state IN('INVENTORY','CAPTURING','SEALED','PUBLISHED','RETRY_WAIT','WAIT_REPORT','FAILED')),
 CHECK(DATEDIFF(date_to,date_from) BETWEEN 0 AND 92)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='读取采集持久检查点；不是广告执行任务';
CREATE TABLE orbit_meta_metric_schedule (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 account_id CHAR(36) NOT NULL COMMENT '原业务账户UUID',
 profile_id CHAR(36) NOT NULL COMMENT '已验证归因配置UUID',
 enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT '默认关闭，必须明确选择才调度',
 interval_seconds INT NOT NULL DEFAULT 900 COMMENT '调度间隔秒，60至86400',
 actor_id BIGINT NOT NULL COMMENT '明确开启调度的用户ID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '调度配置CAS版本',
 next_run_at DATETIME(6) NULL COMMENT '下一次UTC计划时间',
 last_job_id CHAR(36) NULL COMMENT '最近实际生成检查点UUID',
 PRIMARY KEY(tenant_id,account_id,profile_id),
 KEY ix_meta_metric_schedule_due(enabled,next_run_at),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 CHECK(interval_seconds BETWEEN 60 AND 86400),CHECK(revision>=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='明确选择加入的只读采集调度配置';
CREATE TABLE orbit_meta_metric_expected_unit (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '独立冻结库存的检查点UUID',
 dataset VARCHAR(16) NOT NULL COMMENT 'ACCOUNT/CAMPAIGN/ADSET/AD原数据集',
 account_id CHAR(36) NOT NULL COMMENT '原账户UUID',
 business_date DATE NOT NULL COMMENT '独立预期账户业务日',
 profile_id CHAR(36) NOT NULL COMMENT '冻结指标配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '原归因版本',
 owner_user_id CHAR(36) NULL COMMENT '业务日冻结投手，未知保持NULL',
 owner_team_id CHAR(36) NULL COMMENT '业务日冻结团队，未知保持NULL',
 currency CHAR(3) NOT NULL COMMENT '冻结原账户币种，禁止混币种相加',
 timezone_name VARCHAR(64) NOT NULL COMMENT '冻结IANA账户时区',
 account_snapshot_id CHAR(36) NOT NULL COMMENT '独立账户不可变名称快照UUID',
 attribution_version BIGINT NOT NULL COMMENT '冻结归属版本',
 entity_count BIGINT NOT NULL COMMENT '独立库存对象总数，不从Insights行数推算',
 entity_hash CHAR(64) NOT NULL COMMENT '该单元完整有序成员根',
 PRIMARY KEY(tenant_id,job_id,dataset,account_id,business_date),
 KEY ix_meta_metric_expected_latest(tenant_id,profile_id,profile_version,dataset,business_date,account_id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES orbit_meta_metric_job(tenant_id,id),
 CHECK(dataset IN('ACCOUNT','CAMPAIGN','ADSET','AD')),
 CHECK(entity_count>=0 AND attribution_version>=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='采集前独立预期单元，仅覆盖元数据不存指标';
CREATE TABLE orbit_meta_metric_expected_member (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '独立库存检查点UUID',
 dataset VARCHAR(16) NOT NULL COMMENT '原数据集',
 account_id CHAR(36) NOT NULL COMMENT '原账户UUID',
 business_date DATE NOT NULL COMMENT '账户当地业务日',
 profile_id CHAR(36) NOT NULL COMMENT '冻结指标配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '冻结归因版本',
 entity_id CHAR(36) NOT NULL COMMENT '独立库存原实体UUID',
 entity_snapshot_id CHAR(36) NOT NULL COMMENT '原048不可变实体快照UUID',
 name_capture_sequence BIGINT NOT NULL COMMENT '独立名称捕获逻辑序号',
 name_observed_at DATETIME(6) NOT NULL COMMENT '独立名称观察UTC时间',
 PRIMARY KEY(tenant_id,job_id,dataset,account_id,business_date,entity_id),
 FOREIGN KEY(tenant_id,job_id,dataset,account_id,business_date)
 REFERENCES orbit_meta_metric_expected_unit(tenant_id,job_id,dataset,account_id,business_date),
 CHECK(name_capture_sequence>=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='独立库存完整成员流，不通过返回事实补齐分母';
CREATE TABLE orbit_meta_metric_capture_page (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '固定采集检查点UUID',
 page_number INT NOT NULL COMMENT '从一开始连续页号',
 stream_key VARCHAR(80) NOT NULL COMMENT '独立库存或指标请求流固定键',
 request_fingerprint CHAR(64) NOT NULL COMMENT '完整只读请求指纹',
 evidence_sha256 CHAR(64) NOT NULL COMMENT '受控传输原始响应摘要，不存原Token',
 items_json JSON NOT NULL COMMENT '已规范化的只读数据，不含凭据',
 checkpoint_json JSON NULL COMMENT '下一页受控游标；完整末页为空',
 complete BOOLEAN NOT NULL COMMENT '该流是否读到明确完整末页',
 observed_at DATETIME(6) NOT NULL COMMENT '原始页真实观察UTC，不使用查询时间',
 PRIMARY KEY(tenant_id,job_id,stream_key,page_number),
 FOREIGN KEY(tenant_id,job_id) REFERENCES orbit_meta_metric_job(tenant_id,id),
 CHECK(page_number>=1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='页内容与游标同事务暂存，部分页不公开';
CREATE TABLE orbit_meta_metric_publication_receipt (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 publication_id CHAR(36) NOT NULL COMMENT '原048完整发行UUID',
 job_id CHAR(36) NOT NULL COMMENT '独立封存采集检查点UUID',
 binding_json JSON NOT NULL COMMENT '原PublicationValidationReceipt完整规范tuple',
 binding_hash CHAR(64) NOT NULL COMMENT '发行头完整绑定摘要，不能查询时现算自证',
 inventory_hash CHAR(64) NOT NULL COMMENT '独立库存根与checkpoint一致',
 revoked_at DATETIME(6) NULL COMMENT '撤销UTC，不能重新激活旧来源',
 created_at DATETIME(6) NOT NULL COMMENT '完整发布同事务UTC',
 PRIMARY KEY(tenant_id,publication_id),
 UNIQUE KEY uq_meta_metric_receipt_job(tenant_id,job_id),
 FOREIGN KEY(tenant_id,publication_id) REFERENCES orbit_metric_publication(tenant_id,id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES orbit_meta_metric_job(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='受控发行独立回执，不接受浏览器自报来源';
CREATE TRIGGER guard_meta_metric_expected_unit_update BEFORE UPDATE ON orbit_meta_metric_expected_unit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_EXPECTATION_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_expected_unit_delete BEFORE DELETE ON orbit_meta_metric_expected_unit FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_EXPECTATION_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_expected_unit_insert BEFORE INSERT ON orbit_meta_metric_expected_unit FOR EACH ROW
BEGIN
 DECLARE stage VARCHAR(16);
 SELECT state INTO stage FROM orbit_meta_metric_job WHERE tenant_id=NEW.tenant_id AND id=NEW.job_id FOR SHARE;
 IF stage<>'INVENTORY' OR stage IS NULL THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INVENTORY_ALREADY_FROZEN';
 END IF;
END;
CREATE TRIGGER guard_meta_metric_expected_member_update BEFORE UPDATE ON orbit_meta_metric_expected_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_EXPECTATION_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_expected_member_delete BEFORE DELETE ON orbit_meta_metric_expected_member FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_EXPECTATION_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_expected_member_insert BEFORE INSERT ON orbit_meta_metric_expected_member FOR EACH ROW
BEGIN
 DECLARE stage VARCHAR(16);
 SELECT state INTO stage FROM orbit_meta_metric_job WHERE tenant_id=NEW.tenant_id AND id=NEW.job_id FOR SHARE;
 IF stage<>'INVENTORY' OR stage IS NULL THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INVENTORY_ALREADY_FROZEN';
 END IF;
END;
CREATE TRIGGER guard_meta_metric_capture_page_update BEFORE UPDATE ON orbit_meta_metric_capture_page FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_COLLECTION_EVIDENCE_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_capture_page_delete BEFORE DELETE ON orbit_meta_metric_capture_page FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_COLLECTION_EVIDENCE_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_publication_receipt_delete BEFORE DELETE ON orbit_meta_metric_publication_receipt FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_COLLECTION_EVIDENCE_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_receipt_update BEFORE UPDATE ON orbit_meta_metric_publication_receipt FOR EACH ROW
BEGIN
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.publication_id<>OLD.publication_id OR NEW.job_id<>OLD.job_id
 OR NOT (NEW.binding_json<=>OLD.binding_json) OR NEW.binding_hash<>OLD.binding_hash
 OR NEW.inventory_hash<>OLD.inventory_hash OR NEW.created_at<>OLD.created_at
 OR OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_RECEIPT_REVOKE_ONLY';
 END IF;
END;
CREATE TABLE orbit_meta_metric_job_dimension (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '独立库存检查点UUID',
 account_id CHAR(36) NOT NULL COMMENT '原业务账户UUID',
 entity_kind VARCHAR(16) NOT NULL COMMENT '独立库存原实体层级',
 entity_id CHAR(36) NOT NULL COMMENT '真实稳定内部实体UUID',
 entity_snapshot_id CHAR(36) NOT NULL COMMENT '原048不可变实体快照UUID',
 observed_at DATETIME(6) NOT NULL COMMENT '原库存页真实观察UTC',
 PRIMARY KEY(tenant_id,job_id,entity_kind,entity_id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES orbit_meta_metric_job(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id,entity_snapshot_id,entity_kind)
 REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='检查点独立库存到原维度映射，不复用其他采集的名称时刻';
CREATE TABLE orbit_meta_metric_event (
 id CHAR(36) NOT NULL COMMENT '事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '采集检查点UUID',
 actor_id BIGINT NOT NULL COMMENT '当前授权操作者',
 action VARCHAR(40) NOT NULL COMMENT '实际生命周期动作',
 created_at DATETIME(6) NOT NULL COMMENT '实际事务UTC',
 PRIMARY KEY(id),UNIQUE KEY uq_meta_metric_event_tenant(tenant_id,id),
 FOREIGN KEY(tenant_id,job_id) REFERENCES orbit_meta_metric_job(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='采集生命周期审计，不含Token或平台原文';
CREATE TABLE orbit_meta_metric_outbox (
 event_id CHAR(36) NOT NULL COMMENT '同事务事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 created_at DATETIME(6) NOT NULL COMMENT '实际入队UTC',
 PRIMARY KEY(event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES orbit_meta_metric_event(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整发布与审计同事务outbox';
CREATE TRIGGER guard_meta_metric_job_frozen BEFORE UPDATE ON orbit_meta_metric_job FOR EACH ROW
BEGIN
 IF OLD.state='PUBLISHED' OR NEW.tenant_id<>OLD.tenant_id OR NEW.id<>OLD.id
 OR NEW.publication_id<>OLD.publication_id OR NEW.account_id<>OLD.account_id
 OR NEW.connection_id<>OLD.connection_id OR NEW.connection_revision<>OLD.connection_revision
 OR NEW.account_source_revision<>OLD.account_source_revision OR NEW.actor_id<>OLD.actor_id
 OR NEW.profile_id<>OLD.profile_id OR NEW.profile_version<>OLD.profile_version
 OR NEW.profile_hash<>OLD.profile_hash OR NEW.adapter_version<>OLD.adapter_version
 OR NEW.capture_sequence<>OLD.capture_sequence OR NEW.date_from<>OLD.date_from OR NEW.date_to<>OLD.date_to
 OR NEW.api_version<>OLD.api_version OR NEW.source_fingerprint<>OLD.source_fingerprint
 OR NEW.request_hash<>OLD.request_hash OR NEW.created_at<>OLD.created_at
 OR NEW.fencing_token<OLD.fencing_token OR NEW.attempts<OLD.attempts
 OR (OLD.inventory_hash IS NOT NULL AND (NOT (NEW.inventory_hash<=>OLD.inventory_hash)
 OR NEW.expected_unit_count<>OLD.expected_unit_count OR NEW.expected_member_count<>OLD.expected_member_count)) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_COLLECTION_FROZEN_INTENT';
 END IF;
END;
CREATE TRIGGER guard_meta_metric_dimension_insert BEFORE INSERT ON orbit_meta_metric_job_dimension FOR EACH ROW
BEGIN
 DECLARE stage VARCHAR(16);
 SELECT state INTO stage FROM orbit_meta_metric_job WHERE tenant_id=NEW.tenant_id AND id=NEW.job_id FOR SHARE;
 IF stage<>'INVENTORY' OR stage IS NULL THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INVENTORY_ALREADY_FROZEN';
 END IF;
END;
CREATE TRIGGER guard_meta_metric_dimension_update BEFORE UPDATE ON orbit_meta_metric_job_dimension FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INVENTORY_IMMUTABLE';
CREATE TRIGGER guard_meta_metric_dimension_delete BEFORE DELETE ON orbit_meta_metric_job_dimension FOR EACH ROW
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INVENTORY_IMMUTABLE';
CREATE TABLE orbit_meta_metric_insight_index (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 job_id CHAR(36) NOT NULL COMMENT '检查点UUID',
 external_ad_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原平台广告ID，不转数字',
 business_date DATE NOT NULL COMMENT '原返回账户业务日',
 stream_key VARCHAR(80) NOT NULL DEFAULT 'insights' COMMENT '唯一指标流',
 page_number INT NOT NULL COMMENT '原持久分页序号',
 item_index INT NOT NULL COMMENT '原页JSON零起始位置，不另存一套统计值',
 PRIMARY KEY(tenant_id,job_id,external_ad_id,business_date),
 FOREIGN KEY(tenant_id,job_id,stream_key,page_number)
 REFERENCES orbit_meta_metric_capture_page(tenant_id,job_id,stream_key,page_number),
 CHECK(stream_key='insights' AND item_index BETWEEN 0 AND 199)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='只索引受控暂存页，避免逐广告全表扫描；不是平行统计表';
CREATE TRIGGER orbit_meta_metric_insight_index_no_update BEFORE UPDATE ON orbit_meta_metric_insight_index
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INSIGHT_INDEX_IMMUTABLE';
CREATE TRIGGER orbit_meta_metric_insight_index_no_delete BEFORE DELETE ON orbit_meta_metric_insight_index
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INSIGHT_INDEX_IMMUTABLE';
CREATE TRIGGER orbit_meta_metric_insight_index_insert BEFORE INSERT ON orbit_meta_metric_insight_index
FOR EACH ROW BEGIN
 DECLARE stage VARCHAR(16);
 SELECT state INTO stage FROM orbit_meta_metric_job WHERE tenant_id=NEW.tenant_id AND id=NEW.job_id FOR SHARE;
 IF stage<>'CAPTURING' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='META_INSIGHT_INDEX_STAGE'; END IF;
END;
