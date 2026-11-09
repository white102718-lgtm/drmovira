-- 048候选，仅供schema评审；不是migrations，不注册、不执行。
-- 发行权只属于独立可信采集/发行领域，查询Store不能把未知事实授信。
-- 首批只支持ACCOUNT/CAMPAIGN/ADSET/AD；asset/launch映射保留独立绑定，未核验不启用聚合。
-- 查询必须先选最新完整cell，再只JOIN该cell全部facts；最新空cell绝不能回退旧广告行。
CREATE TABLE orbit_metric_fact_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 capture_sequence BIGINT NOT NULL DEFAULT 0 COMMENT '采集开始前分配的单调逻辑序号，不以响应时刻代替',
 published_generation BIGINT NOT NULL DEFAULT 0 COMMENT '已完整发布最大generation，和采集顺序分离',
 PRIMARY KEY(tenant_id),
 FOREIGN KEY(tenant_id) REFERENCES orbit_tenant(id),
 CHECK(capture_sequence BETWEEN 0 AND 9007199254740991),
 CHECK(published_generation BETWEEN 0 AND 9007199254740991)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='指标采集逻辑版本与发行短事务时钟候选';
INSERT INTO orbit_metric_fact_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_metric_publication (
 tenant_id CHAR(36) NOT NULL COMMENT '真实来源租户UUID',
 id CHAR(36) NOT NULL COMMENT '完整发行UUID，公开Metrics.snapshot_id来源',
 generation BIGINT NULL COMMENT '完整发布时分配的单调版本，构建中必须为空',
 profile_id CHAR(36) NOT NULL COMMENT '精确指标配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '完整原profile字符串版本',
 profile_hash CHAR(64) NOT NULL COMMENT '不可变原profile规范摘要',
 authority_kind VARCHAR(16) NOT NULL COMMENT 'TRUSTED或只允许独立UUID库的ISOLATED_TEST',
 source_config_id CHAR(36) NULL COMMENT '真实META_BM来源配置UUID，fixture可空',
 source_config_revision BIGINT NULL COMMENT '取得来源时真实配置版本，禁止猜当前版本',
 source_proof_json JSON NOT NULL COMMENT '最大64KiB完整受控证明，不含Token或平台完整响应',
 state VARCHAR(16) NOT NULL DEFAULT 'BUILDING' COMMENT 'BUILDING、SEALED、PUBLISHED或ABORTED',
 expected_cell_count BIGINT NOT NULL COMMENT '冻结预期account/day/profile单元总数，不由返回行数推算',
 expected_cells_hash CHAR(64) NOT NULL COMMENT '完整预期单元键有序摘要，捕获结果不能改写预期集合',
 captured_cells_hash CHAR(64) NULL COMMENT '实际完整cell键有序摘要，PUBLISHED必须等于原预期',
 cell_count BIGINT NOT NULL DEFAULT 0 COMMENT '实际完整manifest单元数量',
 fact_count BIGINT NOT NULL DEFAULT 0 COMMENT '实际AD粒度版本行数，含明确墓碑',
 capture_sequence_max BIGINT NOT NULL COMMENT '本批最大预先分配采集序号，仅作水位，不替代逐cell顺序',
 manifest_hash CHAR(64) NULL COMMENT '有序完整单元与事实清单根摘要，seal前可空',
 publisher_actor_id BIGINT NOT NULL COMMENT '内部实际发行操作者，不能代替冻结业务owner',
 request_id CHAR(36) NOT NULL COMMENT '本次内部受控发行请求UUID',
 oldest_observed_at DATETIME(3) NULL COMMENT '完整关键单元最旧真实来源UTC时刻，不是提交时间',
 created_at DATETIME(3) NOT NULL COMMENT '内部准备UTC时刻',
 published_at DATETIME(3) NULL COMMENT '完整发布UTC时刻，非平台观察时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_metric_publication_generation(tenant_id,generation),
 UNIQUE KEY uq_metric_publication_anchor(tenant_id,id,generation),
 UNIQUE KEY uq_metric_publication_profile(tenant_id,id,profile_id,profile_version),
 UNIQUE KEY uq_metric_publication_query(tenant_id,id,generation,profile_id,profile_version),
 KEY idx_metric_publication_profile(tenant_id,profile_id,profile_version,state,generation),
 FOREIGN KEY(tenant_id,profile_id,profile_version,profile_hash)
  REFERENCES orbit_metric_profile_version(tenant_id,profile_id,version,payload_hash),
 FOREIGN KEY(tenant_id,source_config_id) REFERENCES orbit_system_configuration(tenant_id,id),
 CHECK(state IN ('BUILDING','SEALED','PUBLISHED','ABORTED')),
 CHECK(authority_kind IN ('TRUSTED','ISOLATED_TEST')),
 CHECK(expected_cell_count>=0 AND cell_count>=0 AND fact_count>=0),
 CHECK(capture_sequence_max BETWEEN 1 AND 9007199254740991),
 CHECK(generation IS NULL OR generation BETWEEN 1 AND 9007199254740991),
 CHECK((state='PUBLISHED')=(generation IS NOT NULL)),
 CHECK(state<>'PUBLISHED' OR (published_at IS NOT NULL AND manifest_hash IS NOT NULL
  AND cell_count=expected_cell_count AND captured_cells_hash IS NOT NULL
  AND captured_cells_hash=expected_cells_hash)),
 CHECK((source_config_id IS NULL)=(source_config_revision IS NULL)),
 CHECK(source_config_revision IS NULL OR source_config_revision BETWEEN 1 AND 9007199254740991),
 CHECK(JSON_TYPE(source_proof_json)='OBJECT' AND JSON_STORAGE_SIZE(source_proof_json)<=65536),
 CHECK(REGEXP_LIKE(expected_cells_hash,'^[0-9a-f]{64}$','c')),
 CHECK(captured_cells_hash IS NULL OR REGEXP_LIKE(captured_cells_hash,'^[0-9a-f]{64}$','c')),
 CHECK(manifest_hash IS NULL OR REGEXP_LIKE(manifest_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整指标批次发行头候选，未发布不允许query读取';

-- 名称只存不可变维度一次；摘要命中必须逐字节核对完整原文/身份/父快照，不以hash代替相等。
CREATE TABLE orbit_metric_entity_snapshot (
 tenant_id CHAR(36) NOT NULL COMMENT '同一来源租户UUID',
 id CHAR(36) NOT NULL COMMENT '不可变完整实体名称与层级快照UUID',
 account_id CHAR(36) NOT NULL COMMENT '真实内部账户UUID，所有层级不得跨账户',
 entity_kind VARCHAR(16) NOT NULL COMMENT 'ACCOUNT、CAMPAIGN、ADSET或AD',
 entity_id CHAR(36) NOT NULL COMMENT '该层真实内部实体UUID，账户层等于account_id',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '原平台数字串，保留前导零',
 name LONGTEXT NOT NULL COMMENT '原名称完整最多10000码点，不截断或制造别名',
 parent_snapshot_id CHAR(36) NULL COMMENT '真实不可变父快照，账户层为空',
 parent_kind VARCHAR(16) NULL COMMENT '真实父层类型，必须和子层对应',
 content_hash CHAR(64) NOT NULL COMMENT '完整原文身份与父快照规范摘要；复用前仍核对原文，不以hash单独授信',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_metric_entity_dedup(tenant_id,account_id,entity_kind,entity_id,content_hash),
 UNIQUE KEY uq_metric_entity_kind(tenant_id,account_id,id,entity_kind),
 UNIQUE KEY uq_metric_entity_parent(tenant_id,account_id,id,entity_kind,entity_id,parent_snapshot_id),
 KEY idx_metric_entity_candidates(tenant_id,entity_kind,account_id,id),
 KEY idx_metric_entity_external(tenant_id,entity_kind,external_id,account_id),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id,parent_snapshot_id,parent_kind)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind),
 CHECK(CHAR_LENGTH(name)<=10000),
 CHECK(REGEXP_LIKE(external_id,'^[0-9]+$','c')),
 CHECK(REGEXP_LIKE(content_hash,'^[0-9a-f]{64}$','c')),
 CHECK((parent_snapshot_id IS NULL)=(parent_kind IS NULL)),
 CHECK((entity_kind='ACCOUNT' AND entity_id=account_id AND parent_snapshot_id IS NULL AND parent_kind IS NULL)
  OR (entity_kind='CAMPAIGN' AND parent_snapshot_id IS NOT NULL AND parent_kind='ACCOUNT')
  OR (entity_kind='ADSET' AND parent_snapshot_id IS NOT NULL AND parent_kind='CAMPAIGN')
  OR (entity_kind='AD' AND parent_snapshot_id IS NOT NULL AND parent_kind='ADSET'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='跨日跨profile复用的不可变实体维度候选，包含搜索不偷换为前缀';

CREATE TABLE orbit_metric_capture_cell (
 tenant_id CHAR(36) NOT NULL COMMENT '来源租户UUID',
 id CHAR(36) NOT NULL COMMENT '本次account/day/profile捕获manifest UUID',
 publication_id CHAR(36) NOT NULL COMMENT '同租户完整发行批次',
 account_id CHAR(36) NOT NULL COMMENT '真实内部账户UUID',
 account_snapshot_id CHAR(36) NOT NULL COMMENT '完整单元冻结的账户名称与平台ID快照，空结果仍保留',
 account_snapshot_kind VARCHAR(16) NOT NULL DEFAULT 'ACCOUNT' COMMENT '组合外键固定账户类型，禁止借广告快照冒充',
 business_date DATE NOT NULL COMMENT '账户当地同名业务日，包含DST，不是UTC或上海切日',
 profile_id CHAR(36) NOT NULL COMMENT '完整原指标配置UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '精确不可变profile版本',
 breakdown_key VARCHAR(16) NOT NULL DEFAULT 'TOTAL' COMMENT '完整单元粒度首期固定TOTAL',
 capture_sequence BIGINT NOT NULL COMMENT '采集前已分配逻辑版本，迟到低版本不得覆盖高版本',
 timezone_name VARCHAR(64) NOT NULL COMMENT '捕获时完整IANA账户时区，当前改时区不重写',
 currency CHAR(3) NOT NULL COMMENT '冻结账户币种，不换汇混加',
 owner_user_id CHAR(36) NULL COMMENT '业务日冻结投手，未归属保持NULL',
 owner_team_id CHAR(36) NULL COMMENT '业务日冻结团队，不默认为当前访问者团队',
 attribution_version BIGINT NOT NULL COMMENT '真实已核历史归属版本，更正发布新版本',
 expected_page_count INT NOT NULL COMMENT '采集清单冻结的全部页数，含完整空页',
 received_page_count INT NOT NULL COMMENT '实际完成的全部页数，未齐不能发布',
 expected_entity_count BIGINT NOT NULL COMMENT '受信对象清单基数，不拿返回metrics行数充当预期',
 fact_count BIGINT NOT NULL COMMENT '完整实际AD版本行数，墓碑单独计入',
 empty_result BOOLEAN NOT NULL COMMENT '完整采集的合法空结果，不把无响应当空',
 empty_field_mask SMALLINT NOT NULL DEFAULT 0 COMMENT '空单元已证合法零字段bit0消费1展示2点击3注册4购物5价值；未知字段无bit',
 critical_complete BOOLEAN NOT NULL COMMENT '原五关键指标与本批规则所需字段均完整的独立证明',
 inventory_hash CHAR(64) NOT NULL COMMENT '完整实体清单/空结果及所有页的规范摘要',
 source_hash CHAR(64) NOT NULL COMMENT '该单元原始受控证据摘要，不存完整平台响应',
 oldest_observed_at DATETIME(3) NOT NULL COMMENT '全部关键页最旧真实UTC观察时刻',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_metric_cell_publication_unit(tenant_id,publication_id,account_id,business_date,profile_id,profile_version,breakdown_key),
 UNIQUE KEY uq_metric_cell_version(tenant_id,account_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence),
 UNIQUE KEY uq_metric_cell_fact_binding(tenant_id,id,account_id,account_snapshot_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence),
 KEY idx_metric_cell_latest(tenant_id,profile_id,profile_version,business_date,account_id,capture_sequence DESC),
 KEY idx_metric_cell_owner(tenant_id,owner_user_id,business_date,profile_id,account_id),
 KEY idx_metric_cell_team(tenant_id,owner_team_id,business_date,profile_id,account_id),
 FOREIGN KEY(tenant_id,publication_id,profile_id,profile_version)
  REFERENCES orbit_metric_publication(tenant_id,id,profile_id,profile_version),
 FOREIGN KEY(tenant_id,account_id) REFERENCES orbit_ad_account(tenant_id,id),
 FOREIGN KEY(tenant_id,account_id,account_snapshot_id,account_snapshot_kind)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind),
 CHECK(account_snapshot_kind='ACCOUNT'),
 CHECK(capture_sequence BETWEEN 1 AND 9007199254740991),
 CHECK(attribution_version BETWEEN 1 AND 9007199254740991),
 CHECK(breakdown_key='TOTAL'),
 CHECK(expected_page_count>=1 AND received_page_count=expected_page_count),
 CHECK(expected_entity_count>=0 AND fact_count>=0),
 CHECK(empty_field_mask BETWEEN 0 AND 63),
 CHECK(empty_result OR empty_field_mask=0),
 CHECK(NOT (empty_result AND critical_complete) OR (empty_field_mask & 55)=55),
 CHECK(NOT empty_result OR (expected_entity_count=0 AND fact_count=0)),
 CHECK(REGEXP_LIKE(inventory_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(source_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='完整预期单元manifest候选，coverage分母不来自返回行数';

CREATE TABLE orbit_metric_ad_fact_version (
 tenant_id CHAR(36) NOT NULL COMMENT '冻结租户UUID',
 id CHAR(36) NOT NULL COMMENT '不可变单条AD日版本UUID，供映射绑定',
 cell_id CHAR(36) NOT NULL COMMENT '同租户完整捕获manifest',
 account_id CHAR(36) NOT NULL COMMENT '真实账户UUID，与cell完整组合外键核对',
 business_date DATE NOT NULL COMMENT '同cell账户当地业务日',
 profile_id CHAR(36) NOT NULL COMMENT '原profile UUID',
 profile_version VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '精确profile版本，不偷混当前头',
 capture_sequence BIGINT NOT NULL COMMENT '同cell采集前逻辑版本',
 breakdown_key VARCHAR(16) NOT NULL DEFAULT 'TOTAL' COMMENT '首期仅TOTAL，不把分解行混入总计',
 ad_id CHAR(36) NOT NULL COMMENT '真实内部AD UUID，不能用TaskNode替代',
 adset_id CHAR(36) NOT NULL COMMENT '同账户真实内部父广告组UUID',
 campaign_id CHAR(36) NOT NULL COMMENT '同账户真实内部父系列UUID',
 account_snapshot_id CHAR(36) NOT NULL COMMENT '与cell完全相同的账户不可变快照',
 account_snapshot_kind VARCHAR(16) NOT NULL DEFAULT 'ACCOUNT' COMMENT '固定ACCOUNT的外键类型',
 campaign_snapshot_id CHAR(36) NOT NULL COMMENT '完整系列快照，父必须是本条账户快照',
 campaign_snapshot_kind VARCHAR(16) NOT NULL DEFAULT 'CAMPAIGN' COMMENT '固定CAMPAIGN的外键类型',
 adset_snapshot_id CHAR(36) NOT NULL COMMENT '完整组快照，父必须是本条系列快照',
 adset_snapshot_kind VARCHAR(16) NOT NULL DEFAULT 'ADSET' COMMENT '固定ADSET的外键类型',
 ad_snapshot_id CHAR(36) NOT NULL COMMENT '完整广告快照，父必须是本条广告组快照',
 ad_snapshot_kind VARCHAR(16) NOT NULL DEFAULT 'AD' COMMENT '固定AD的外键类型',
 channel_id CHAR(36) NULL COMMENT 'AD冻结渠道UUID，未知保持NULL，不借当前目录回填',
 product_name_snapshot VARCHAR(100) NULL COMMENT '真实历史产品名，未知NULL',
 parent_mapping_hash CHAR(64) NOT NULL COMMENT '同账户完整真实父树绑定摘要，发行方核验',
 asset_mapping_state VARCHAR(16) NOT NULL DEFAULT 'UNKNOWN' COMMENT 'UNKNOWN、VERIFIED、AMBIGUOUS或UNMAPPED',
 asset_mapping_hash CHAR(64) NULL COMMENT '本版本完整creative到asset映射摘要，缺失不授usage',
 launch_mapping_hash CHAR(64) NULL COMMENT '真实自动创建计划映射摘要，无映射不按名字猜',
 is_deleted BOOLEAN NOT NULL DEFAULT 0 COMMENT '本grain新版本逻辑墓碑，必须选最新版本后过滤',
 spend DECIMAL(34,6) NULL COMMENT '原规范金额，不足来源NULL；发行前必须检查原字符串28字符及6小数',
 impressions DECIMAL(34,6) NULL COMMENT '真实展示可加分子，缺失NULL不补0',
 clicks DECIMAL(34,6) NULL COMMENT '真实点击可加分子，缺失NULL',
 registrations DECIMAL(34,6) NULL COMMENT 'profile映射的真实注册，未知NULL',
 purchases DECIMAL(34,6) NULL COMMENT 'profile映射的真实购买，首期CPA分母',
 purchase_value DECIMAL(34,6) NULL COMMENT '同cell币种真实购买价值，未知NULL',
 observed_at DATETIME(3) NOT NULL COMMENT '真实来源UTC观察时间，不用查询时间伪造新鲜度',
 fact_hash CHAR(64) NOT NULL COMMENT '本条完整不可变tuple摘要，不只hash金额',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_metric_ad_grain(tenant_id,account_id,ad_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence),
 KEY idx_metric_ad_candidate(tenant_id,profile_id,profile_version,business_date,account_id,ad_id,capture_sequence DESC),
 KEY idx_metric_ad_cell(tenant_id,cell_id,id),
 KEY idx_metric_ad_campaign(tenant_id,campaign_id,business_date,profile_id,capture_sequence),
 KEY idx_metric_ad_adset(tenant_id,adset_id,business_date,profile_id,capture_sequence),
 FOREIGN KEY(tenant_id,cell_id,account_id,account_snapshot_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence)
  REFERENCES orbit_metric_capture_cell(tenant_id,id,account_id,account_snapshot_id,business_date,profile_id,profile_version,breakdown_key,capture_sequence),
 FOREIGN KEY(tenant_id,account_id,account_snapshot_id,account_snapshot_kind)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind),
 FOREIGN KEY(tenant_id,account_id,campaign_snapshot_id,campaign_snapshot_kind,campaign_id,account_snapshot_id)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind,entity_id,parent_snapshot_id),
 FOREIGN KEY(tenant_id,account_id,adset_snapshot_id,adset_snapshot_kind,adset_id,campaign_snapshot_id)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind,entity_id,parent_snapshot_id),
 FOREIGN KEY(tenant_id,account_id,ad_snapshot_id,ad_snapshot_kind,ad_id,adset_snapshot_id)
  REFERENCES orbit_metric_entity_snapshot(tenant_id,account_id,id,entity_kind,entity_id,parent_snapshot_id),
 CHECK(breakdown_key='TOTAL'),
 CHECK(account_snapshot_kind='ACCOUNT' AND campaign_snapshot_kind='CAMPAIGN'
  AND adset_snapshot_kind='ADSET' AND ad_snapshot_kind='AD'),
 CHECK(asset_mapping_state IN ('UNKNOWN','VERIFIED','AMBIGUOUS','UNMAPPED')),
 CHECK(asset_mapping_state<>'VERIFIED' OR asset_mapping_hash IS NOT NULL),
 CHECK(spend IS NULL OR spend>=0),
 CHECK(impressions IS NULL OR impressions>=0),
 CHECK(clicks IS NULL OR clicks>=0),
 CHECK(registrations IS NULL OR registrations>=0),
 CHECK(purchases IS NULL OR purchases>=0),
 CHECK(purchase_value IS NULL OR purchase_value>=0),
 CHECK(REGEXP_LIKE(parent_mapping_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(fact_hash,'^[0-9a-f]{64}$','c')),
 CHECK(asset_mapping_hash IS NULL OR REGEXP_LIKE(asset_mapping_hash,'^[0-9a-f]{64}$','c')),
 CHECK(launch_mapping_hash IS NULL OR REGEXP_LIKE(launch_mapping_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='只消费最新完整cell内AD日版本候选，墓碑后过滤，不从旧cell补漏';

CREATE TABLE orbit_metric_fact_asset_binding (
 tenant_id CHAR(36) NOT NULL COMMENT '真实租户UUID',
 fact_id CHAR(36) NOT NULL COMMENT '绑定具体AD日版本，不绑定可变当前广告名',
 asset_id CHAR(36) NOT NULL COMMENT '已核本地素材UUID',
 asset_revision BIGINT NOT NULL COMMENT '实际观察时素材版本，历史不随当前编辑重写',
 creative_external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '实际核验的创意平台数字ID',
 mapping_hash CHAR(64) NOT NULL COMMENT '当前fact完整映射根摘要',
 evidence_hash CHAR(64) NOT NULL COMMENT '独立ad到creative到asset来源证据摘要',
 PRIMARY KEY(tenant_id,fact_id,asset_id,creative_external_id),
 FOREIGN KEY(tenant_id,fact_id) REFERENCES orbit_metric_ad_fact_version(tenant_id,id),
 FOREIGN KEY(tenant_id,asset_id) REFERENCES orbit_material_asset(tenant_id,id),
 CHECK(asset_revision BETWEEN 1 AND 9007199254740991),
 CHECK(REGEXP_LIKE(creative_external_id,'^[0-9]+$','c')),
 CHECK(REGEXP_LIKE(mapping_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(evidence_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='只读历史素材使用映射候选，不表示当前素材可执行或可分配';

CREATE TABLE orbit_metric_fact_launch_binding (
 tenant_id CHAR(36) NOT NULL COMMENT '同一租户UUID',
 fact_id CHAR(36) NOT NULL COMMENT '具体AD日版本UUID',
 plan_id CHAR(36) NOT NULL COMMENT '真实自动创建归属的计划UUID，不通过名称推断',
 source_revision BIGINT NOT NULL COMMENT '真实执行冻结配置版本',
 ad_local_id CHAR(36) NOT NULL COMMENT '真实命名与执行映射中的广告local_id',
 mapping_hash CHAR(64) NOT NULL COMMENT '完整真实自动创建映射摘要',
 evidence_hash CHAR(64) NOT NULL COMMENT '成功回读真实ad_id与计划关系的证据摘要',
 PRIMARY KEY(tenant_id,fact_id),
 FOREIGN KEY(tenant_id,fact_id) REFERENCES orbit_metric_ad_fact_version(tenant_id,id),
 FOREIGN KEY(tenant_id,plan_id,source_revision) REFERENCES orbit_launch_plan_version(tenant_id,plan_id,revision),
 CHECK(source_revision BETWEEN 1 AND 9007199254740991),
 CHECK(REGEXP_LIKE(mapping_hash,'^[0-9a-f]{64}$','c')),
 CHECK(REGEXP_LIKE(evidence_hash,'^[0-9a-f]{64}$','c'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='自动投放统计真实归属候选，不包含手工创建或按名匹配';

-- 发布头一旦PUBLISHED不可改写/删除。所有子表发布后必须拒绝I/U/D，避免已冻结generation漂移。
CREATE TRIGGER metric_entity_snapshot_immutable_update BEFORE UPDATE ON orbit_metric_entity_snapshot
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_ENTITY_SNAPSHOT_IMMUTABLE';
CREATE TRIGGER metric_entity_snapshot_immutable_delete BEFORE DELETE ON orbit_metric_entity_snapshot
 FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_ENTITY_SNAPSHOT_IMMUTABLE';
CREATE TRIGGER metric_fact_clock_monotonic BEFORE UPDATE ON orbit_metric_fact_clock
 FOR EACH ROW BEGIN
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.capture_sequence<OLD.capture_sequence
  OR NEW.published_generation<OLD.published_generation THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CLOCK_REGRESSION';
 END IF;
 END;
CREATE TRIGGER metric_publication_intent_guard BEFORE UPDATE ON orbit_metric_publication
 FOR EACH ROW BEGIN
 IF NOT (NEW.tenant_id<=>OLD.tenant_id) OR NOT (NEW.id<=>OLD.id)
  OR NOT (NEW.profile_id<=>OLD.profile_id) OR NOT (NEW.profile_version<=>OLD.profile_version)
  OR NOT (NEW.profile_hash<=>OLD.profile_hash) OR NOT (NEW.authority_kind<=>OLD.authority_kind)
  OR NOT (NEW.source_config_id<=>OLD.source_config_id)
  OR NOT (NEW.source_config_revision<=>OLD.source_config_revision)
  OR NOT (NEW.source_proof_json<=>OLD.source_proof_json)
  OR NOT (NEW.expected_cell_count<=>OLD.expected_cell_count)
  OR NOT (NEW.expected_cells_hash<=>OLD.expected_cells_hash)
  OR NOT (NEW.capture_sequence_max<=>OLD.capture_sequence_max)
  OR NOT (NEW.publisher_actor_id<=>OLD.publisher_actor_id) OR NOT (NEW.request_id<=>OLD.request_id)
  OR NOT (NEW.created_at<=>OLD.created_at)
 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLICATION_INTENT_IMMUTABLE';
 END IF;
 END;
CREATE TRIGGER metric_publication_immutable_update BEFORE UPDATE ON orbit_metric_publication
 FOR EACH ROW BEGIN
 IF OLD.state='PUBLISHED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLICATION_IMMUTABLE';
 END IF;
 END;
CREATE TRIGGER metric_publication_immutable_delete BEFORE DELETE ON orbit_metric_publication
 FOR EACH ROW BEGIN
 IF OLD.state='PUBLISHED' THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLICATION_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_cell_insert_guard BEFORE INSERT ON orbit_metric_capture_cell
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT state INTO publication_state FROM orbit_metric_publication WHERE tenant_id=NEW.tenant_id AND id=NEW.publication_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_cell_update_guard BEFORE UPDATE ON orbit_metric_capture_cell
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT state INTO publication_state FROM orbit_metric_publication WHERE tenant_id=OLD.tenant_id AND id=OLD.publication_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.publication_id<>OLD.publication_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_cell_delete_guard BEFORE DELETE ON orbit_metric_capture_cell
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT state INTO publication_state FROM orbit_metric_publication WHERE tenant_id=OLD.tenant_id AND id=OLD.publication_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING','ABORTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_insert_guard BEFORE INSERT ON orbit_metric_ad_fact_version
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_capture_cell c JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.cell_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_update_guard BEFORE UPDATE ON orbit_metric_ad_fact_version
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_capture_cell c JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE c.tenant_id=OLD.tenant_id AND c.id=OLD.cell_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.cell_id<>OLD.cell_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_delete_guard BEFORE DELETE ON orbit_metric_ad_fact_version
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_capture_cell c JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE c.tenant_id=OLD.tenant_id AND c.id=OLD.cell_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING','ABORTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_asset_insert_guard BEFORE INSERT ON orbit_metric_fact_asset_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=NEW.tenant_id AND f.id=NEW.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_asset_update_guard BEFORE UPDATE ON orbit_metric_fact_asset_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=OLD.tenant_id AND f.id=OLD.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.fact_id<>OLD.fact_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_asset_delete_guard BEFORE DELETE ON orbit_metric_fact_asset_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=OLD.tenant_id AND f.id=OLD.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING','ABORTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_launch_insert_guard BEFORE INSERT ON orbit_metric_fact_launch_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=NEW.tenant_id AND f.id=NEW.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_launch_update_guard BEFORE UPDATE ON orbit_metric_fact_launch_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=OLD.tenant_id AND f.id=OLD.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.fact_id<>OLD.fact_id THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_CHILD_PARENT_IMMUTABLE';
 END IF;
 END;

CREATE TRIGGER metric_fact_launch_delete_guard BEFORE DELETE ON orbit_metric_fact_launch_binding
 FOR EACH ROW BEGIN
 DECLARE publication_state VARCHAR(16) DEFAULT NULL;
 SELECT p.state INTO publication_state FROM orbit_metric_ad_fact_version f JOIN orbit_metric_capture_cell c ON c.tenant_id=f.tenant_id AND c.id=f.cell_id JOIN orbit_metric_publication p ON p.tenant_id=c.tenant_id AND p.id=c.publication_id WHERE f.tenant_id=OLD.tenant_id AND f.id=OLD.fact_id FOR SHARE;
 IF publication_state IS NULL OR publication_state NOT IN ('BUILDING','ABORTED') THEN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='METRIC_PUBLISHED_CHILD_IMMUTABLE';
 END IF;
 END;
