-- Python账户与导入业务基础；由主任务显式迁移，不注册菜单、不连接外部平台。
CREATE TABLE orbit_account_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID；写入由当前会话确定',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '账户目录与导入写入版本，绑定稳定续页',
 PRIMARY KEY (tenant_id),
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户短事务串行版本锁；不是广告事实水位';
INSERT INTO orbit_account_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_ad_account (
 tenant_id CHAR(36) NOT NULL COMMENT '账户当前授权租户UUID',
 id CHAR(36) NOT NULL COMMENT '内部账户业务UUID；外部数字ID不能代替',
 external_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '平台纯数字ID，保留前导零，不转整数',
 name LONGTEXT NOT NULL COMMENT '平台原始账户名称，服务层限制10000码点，不截断原文',
 name_prefix VARCHAR(191) NOT NULL COMMENT '原名称前191码点，用于有界前缀搜索；不替代原文',
 owner_user_id CHAR(36) NOT NULL COMMENT '当前明确归属投手业务UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '当前归属团队业务UUID',
 vendor_id CHAR(36) NULL COMMENT '当前最小户商引用UUID；解绑不删除历史',
 currency CHAR(3) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '服务端ISO4217白名单币种，未知不能写金额',
 timezone_id VARCHAR(64) NOT NULL COMMENT '有效IANA账户时区，不存固定偏移替代夏令时',
 auth_status VARCHAR(16) NOT NULL COMMENT 'AUTHORIZED、EXPIRED、REVOKED或UNKNOWN',
 account_status VARCHAR(16) NOT NULL COMMENT 'ACTIVE、DISABLED或UNKNOWN；不猜测平台原始状态',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '乐观锁业务版本，最大安全整数约束在服务层',
 value_json JSON NOT NULL COMMENT '原Account公开合同的完整快照，金额未知必须为null',
 details_json JSON NOT NULL COMMENT '独立详情扩展及来源时间；不得含Token或平台原始敏感响应',
 synced_at DATETIME(3) NULL COMMENT '实际元数据成功同步UTC时刻，未取得为NULL',
 bound_at DATETIME(3) NOT NULL COMMENT '本地首次成功绑定UTC时刻；更早事实不追授当前投手',
 unbound_at DATETIME(3) NULL COMMENT '本地解绑UTC时刻；不代表平台广告被删除',
 created_at DATETIME(3) NOT NULL COMMENT '本系统记录创建UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_account_external (tenant_id,external_id) COMMENT '同租户同平台账户仅一个当前对象；导入不得重绑',
 KEY idx_account_owner (tenant_id,owner_user_id,id) COMMENT '普通用户本人与UUID稳定分页',
 KEY idx_account_team (tenant_id,owner_team_id,id) COMMENT '明确管理团队内的UUID稳定分页',
 KEY idx_account_state (tenant_id,account_status,auth_status,id) COMMENT '状态和授权状态筛选',
 KEY idx_account_vendor (tenant_id,vendor_id,id) COMMENT '按可读户商筛选账户',
 KEY idx_account_name (tenant_id,name_prefix,id) COMMENT '名称前缀搜索，禁止无范围全表包含扫描',
 KEY idx_account_created (tenant_id,created_at,id) COMMENT '登记日期端点包含及稳定分页'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户当前可读目录，不是归属历史或广告事实汇总';

CREATE TABLE orbit_account_assignment (
 tenant_id CHAR(36) NOT NULL COMMENT '归属区间所属租户UUID',
 id CHAR(36) NOT NULL COMMENT '稳定归属区间UUID',
 account_id CHAR(36) NOT NULL COMMENT '内部账户业务UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '冻结投手业务UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '冻结团队业务UUID',
 vendor_id CHAR(36) NULL COMMENT '冻结户商UUID，不回写历史快照',
 starts_at DATETIME(3) NOT NULL COMMENT '区间开始UTC，按账户IANA时区下一业务日规则计算',
 ends_at DATETIME(3) NULL COMMENT '区间结束UTC且不包含此时刻；NULL代表未结束',
 reason VARCHAR(1000) NOT NULL COMMENT '本地绑定或分配原因，不包含凭据',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '分配区间业务版本',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_account_assignment_start (tenant_id,account_id,starts_at) COMMENT '账户同一开始时刻唯一；重叠仍需锁定账户后校验',
 KEY idx_assignment_owner (tenant_id,owner_user_id,starts_at,account_id) COMMENT '历史归属按冻结拥有者和日期查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='不可偷改历史归属；未来转移只创建合法不重叠区间';

CREATE TABLE orbit_account_import (
 tenant_id CHAR(36) NOT NULL COMMENT '由会话确认的租户UUID',
 id CHAR(36) NOT NULL COMMENT '导入批次业务UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '批次版本，重试必须CAS',
 vendor_id CHAR(36) NOT NULL COMMENT '已授权AVAILABLE户商引用UUID',
 vendor_revision BIGINT NOT NULL COMMENT '冻结户商版本，执行前再次核验',
 owner_user_id CHAR(36) NOT NULL COMMENT '冻结目标投手业务UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '冻结目标团队业务UUID',
 actor_id BIGINT NOT NULL COMMENT '最初发起人的原生用户ID；Worker发送前重新授权',
 actor_subject_id CHAR(36) NOT NULL COMMENT '最初发起人的业务用户UUID',
 scope_version BIGINT NOT NULL COMMENT '冻结权限版本，不能绕过即时撤权',
 input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整原始输入UTF8的SHA256，不按去重结果算hash',
 input_ref CHAR(36) NOT NULL COMMENT '服务端原始输入对象UUID，不返回文件路径',
 state VARCHAR(20) NOT NULL COMMENT 'QUEUED、RUNNING、SUCCEEDED、PARTIAL_SUCCESS或FAILED',
 total INT NOT NULL COMMENT '原始非空token总数，含重复和非法项，最多500',
 success_count INT NOT NULL DEFAULT 0 COMMENT 'SUCCEEDED和ALREADY_EXISTS之和，不计重复项',
 failed_count INT NOT NULL DEFAULT 0 COMMENT '非法、无权、归属冲突和失败项数量',
 duplicate_count INT NOT NULL DEFAULT 0 COMMENT '重复项数量，不计为失败',
 created_at DATETIME(3) NOT NULL COMMENT '受理UTC时刻，不等于平台成功',
 updated_at DATETIME(3) NOT NULL COMMENT '最新批次变化UTC时刻',
 PRIMARY KEY (tenant_id,id),
 KEY idx_import_actor (tenant_id,actor_subject_id,id) COMMENT '按真实发起人有界分页',
 KEY idx_import_owner (tenant_id,owner_user_id,id) COMMENT '拥有者范围内有界批次查询',
 KEY idx_import_team (tenant_id,owner_team_id,id) COMMENT '显式管理团队批次查询',
 KEY idx_import_state (tenant_id,state,id) COMMENT '批次状态及UUID续页',
 KEY idx_import_created (tenant_id,created_at,id) COMMENT '登记日期范围批次查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='持久化导入批次，202仅代表受理';

CREATE TABLE orbit_account_import_row (
 tenant_id CHAR(36) NOT NULL COMMENT '批次所属可信租户UUID',
 id CHAR(36) NOT NULL COMMENT '稳定导入行UUID，重试沿用不换新行',
 batch_id CHAR(36) NOT NULL COMMENT '所属批次UUID',
 token_index INT NOT NULL COMMENT '从0开始的原始token顺序，包含重复和非法项',
 line_no INT NOT NULL COMMENT '原始文本行号，从1开始，CRLF算一行',
 column_no INT NOT NULL COMMENT '原始行内Unicode码点列号，从1开始',
 raw_display VARCHAR(128) NOT NULL COMMENT '原始token前128码点，只作解释展示',
 normalized_id VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '仅去act_前缀的有效数字串，非法项NULL',
 duplicate_of INT NULL COMMENT '首个有效重复token的原始索引，首项0不能误判为空',
 state VARCHAR(24) NOT NULL COMMENT 'WAITING/FETCHING及七种合同终态',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '认领栅栏版本，迟到结果不能覆盖新尝试',
 attempts INT NOT NULL DEFAULT 0 COMMENT '实际开始的只读元数据尝试次数，最多三次',
 next_attempt_at DATETIME(3) NULL COMMENT '限流退避后允许认领UTC时刻',
 claimed_at DATETIME(3) NULL COMMENT 'FETCHING认领UTC时刻，120秒租约',
 account_id CHAR(36) NULL COMMENT '成功绑定或明确已存在的内部UUID；无权时不泄露',
 value_json JSON NOT NULL COMMENT '原ImportRow公开结果，未知消费不补零，不存平台原始响应',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_import_token (tenant_id,batch_id,token_index) COMMENT '每个原始token恰有一行结果',
 KEY idx_import_claim (state,next_attempt_at,tenant_id,id) COMMENT '跨批次有界SKIP LOCKED认领',
 KEY idx_import_recover (state,claimed_at,tenant_id,id) COMMENT '120秒租约恢复有界读取'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='逐token导入状态，去重前限额，未知结果不冒充成功';

CREATE TABLE orbit_account_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 actor_id BIGINT NOT NULL COMMENT '真实发起人原生用户ID',
 request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '逐字节幂等键，同键不能更换意图',
 payload_hash CHAR(64) NOT NULL COMMENT '路径、户商、归属及原始输入的规范摘要',
 response_json JSON NOT NULL COMMENT '首次提交回执，不包含Token',
 created_at DATETIME(3) NOT NULL COMMENT '幂等提交UTC时刻',
 PRIMARY KEY (tenant_id,actor_id,request_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='账户命令幂等，与批次/审计/outbox同事务';

CREATE TABLE orbit_account_event (
 id CHAR(36) NOT NULL COMMENT '稳定审计事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '对象可信租户UUID',
 resource_type VARCHAR(24) NOT NULL COMMENT 'ACCOUNT或IMPORT及ROW',
 resource_id CHAR(36) NOT NULL COMMENT '对应业务对象UUID',
 revision BIGINT NOT NULL COMMENT '操作后版本',
 actor_id BIGINT NOT NULL COMMENT '最初发起人，不用Worker冒充业务拥有者',
 request_id CHAR(36) NOT NULL COMMENT '服务端请求关联UUID',
 action VARCHAR(32) NOT NULL COMMENT '受理、认领、完成、分配、同步或本地解绑',
 details_json JSON NOT NULL COMMENT '固定状态与摘要，不保存原始输入或秘密',
 created_at DATETIME(3) NOT NULL COMMENT '真实UTC提交时刻',
 PRIMARY KEY (id),
 UNIQUE KEY uk_account_event_version (tenant_id,resource_type,resource_id,revision) COMMENT '对象版本只追加一次审计',
 KEY idx_account_event_time (tenant_id,created_at,id) COMMENT '审计按时间及UUID续页'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='只追加账户与导入审计';

CREATE TABLE orbit_account_outbox (
 event_id CHAR(36) NOT NULL COMMENT '关联审计事件UUID，消费者去重键',
 tenant_id CHAR(36) NOT NULL COMMENT '可信租户UUID',
 resource_type VARCHAR(24) NOT NULL COMMENT '对应账户或导入事件类别',
 resource_id CHAR(36) NOT NULL COMMENT '对象业务UUID',
 created_at DATETIME(3) NOT NULL COMMENT '与事件同事务UTC时刻',
 processed_at DATETIME(3) NULL COMMENT '消费者实际完成时刻，未完成NULL',
 PRIMARY KEY (event_id),
 KEY idx_account_outbox_pending (processed_at,created_at,event_id) COMMENT '有界未处理事件认领'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='事务outbox，创建记录不等于处理完成';
