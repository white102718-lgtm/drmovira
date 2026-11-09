-- PY06独立计划/模板内部持久化。只建表，不导入Java完成状态，不创建广告任务。
CREATE TABLE orbit_launch_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 plan_revision BIGINT NOT NULL DEFAULT 0 COMMENT '计划任何实际写入后的分页水位',
 template_revision BIGINT NOT NULL DEFAULT 0 COMMENT '模板及冻结共享集合实际写入后的分页水位',
 PRIMARY KEY (tenant_id),
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='投放配置租户短事务锁和列表版本，不代替目录或账户水位';
INSERT INTO orbit_launch_clock(tenant_id) SELECT id FROM orbit_tenant;

CREATE TABLE orbit_launch_plan (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 id CHAR(36) NOT NULL COMMENT '计划稳定业务UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '唯一拥有者业务UUID，不是原若依整型ID',
 owner_team_id CHAR(36) NOT NULL COMMENT '唯一拥有者所属团队UUID，写前实时复验',
 channel_id CHAR(36) NULL COMMENT '当前选择渠道UUID，空引用草稿允许NULL',
 name VARCHAR(100) NOT NULL COMMENT '计划名称NFC后一百码点，草稿可空',
 state VARCHAR(16) NOT NULL COMMENT 'DRAFT、VALIDATED、SUBMITTED或ARCHIVED；缺真实预检不得进入VALIDATED',
 revision BIGINT NOT NULL COMMENT '每次实际保存后的CAS版本，JavaScript安全整数',
 payload_json JSON NOT NULL COMMENT '原PlanWrite严格合同完整配置，正文不超过五MiB',
 payload_hash CHAR(64) NOT NULL COMMENT '规范配置SHA256，用于幂等差异，不是可执行预检hash',
 payload_bytes INT UNSIGNED NOT NULL COMMENT '规范配置UTF8字节数，分页先读元数据控制整页内存',
 account_count SMALLINT UNSIGNED NOT NULL COMMENT '已选账户零至五百，概览不读取大型JSON',
 asset_count SMALLINT UNSIGNED NOT NULL COMMENT '已选素材零至五百，概览不逐行查关联',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻',
 updated_at DATETIME(3) NOT NULL COMMENT '最后实际保存UTC时刻，失败或无变化不更新',
 PRIMARY KEY (tenant_id,id),
 KEY idx_launch_owner (tenant_id,owner_user_id,id) COMMENT '本人范围UUID键集分页',
 KEY idx_launch_team (tenant_id,owner_team_id,id) COMMENT '显式管理团队UUID键集分页',
 KEY idx_launch_state (tenant_id,state,id) COMMENT '状态组合过滤续页，不深OFFSET',
 KEY idx_launch_channel (tenant_id,channel_id,id) COMMENT '渠道关联定位及当前引用检查',
 KEY idx_launch_updated (tenant_id,updated_at,id) COMMENT '后台按更新时间有界维护',
 FOREIGN KEY (tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY (tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 FOREIGN KEY (tenant_id,channel_id) REFERENCES orbit_channel(tenant_id,id),
 CONSTRAINT ck_launch_revision CHECK (revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_launch_state CHECK (state IN ('DRAFT','VALIDATED','SUBMITTED','ARCHIVED')),
 CONSTRAINT ck_launch_reference_counts CHECK (account_count<=500 AND asset_count<=500)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实服务器投放草稿与计划；原始大配置仅详情读取';

CREATE TABLE orbit_launch_plan_version (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 plan_id CHAR(36) NOT NULL COMMENT '对应计划稳定UUID',
 revision BIGINT NOT NULL COMMENT '不可变计划配置版本',
 payload_json JSON NOT NULL COMMENT '该次保存完整配置快照，后续编辑不覆写',
 payload_hash CHAR(64) NOT NULL COMMENT '该版本规范配置SHA256',
 dependency_json JSON NOT NULL COMMENT '当前已验证引用版本及权限范围指纹；未知依赖不得伪填已验证',
 created_at DATETIME(3) NOT NULL COMMENT '该版本写入UTC时刻',
 created_by BIGINT NOT NULL COMMENT '实际保存者原若依用户ID',
 PRIMARY KEY (tenant_id,plan_id,revision),
 FOREIGN KEY (tenant_id,plan_id) REFERENCES orbit_launch_plan(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='计划每次真实保存不可变快照；不冒充执行任务快照';

CREATE TABLE orbit_launch_plan_reference (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 plan_id CHAR(36) NOT NULL COMMENT '当前计划UUID',
 kind VARCHAR(16) NOT NULL COMMENT 'ACCOUNT或ASSET，有界集合用于反向定位',
 reference_id CHAR(36) NOT NULL COMMENT '已实时验证同租户来源业务UUID',
 source_revision BIGINT NOT NULL COMMENT '真实来源版本，非显示名称推算',
 PRIMARY KEY (tenant_id,plan_id,kind,reference_id),
 KEY idx_launch_reference (tenant_id,kind,reference_id,plan_id) COMMENT '来源变更定位计划，不扫描JSON',
 FOREIGN KEY (tenant_id,plan_id) REFERENCES orbit_launch_plan(tenant_id,id),
 CONSTRAINT ck_launch_reference_kind CHECK (kind IN ('ACCOUNT','ASSET'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='当前计划账户素材归一化有界引用；权限仍复验真实来源';

CREATE TABLE orbit_launch_template (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 id CHAR(36) NOT NULL COMMENT '模板稳定业务UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '唯一模板所有者业务UUID，非所有者不可编辑',
 owner_team_id CHAR(36) NOT NULL COMMENT '模板所有者团队UUID',
 name VARCHAR(80) NOT NULL COMMENT 'NFC模板名称，按租户及所有者唯一，归档不释放名称',
 description VARCHAR(500) NOT NULL COMMENT '纯文本模板说明，最多五百码点',
 visibility VARCHAR(8) NOT NULL COMMENT 'PRIVATE或TEAM；TEAM仅冻结显式当前接收者',
 state VARCHAR(16) NOT NULL COMMENT 'ACTIVE或ARCHIVED，归档不硬删除',
 revision BIGINT NOT NULL COMMENT '模板CAS安全整数版本',
 config_json JSON NOT NULL COMMENT '只含原系列配置和素材类型要求；无账户身份渠道或分配',
 config_hash CHAR(64) NOT NULL COMMENT '规范模板内容SHA256，不作为预检凭证',
 config_bytes INT UNSIGNED NOT NULL COMMENT '完整模板响应规范配置字节数，用于有界载入原合同列表',
 created_at DATETIME(3) NOT NULL COMMENT '创建UTC时刻，内部审计使用',
 updated_at DATETIME(3) NOT NULL COMMENT '实际修改UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_template_owner_name (tenant_id,owner_user_id,name) COMMENT 'NFC且区分大小写重名约束，所有状态不复用',
 KEY idx_template_owner (tenant_id,owner_user_id,id) COMMENT '本人所有模板键集分页',
 KEY idx_template_team (tenant_id,owner_team_id,id) COMMENT '当前显式管理团队过滤',
 KEY idx_template_state (tenant_id,state,id) COMMENT '当前状态列表有界续页',
 FOREIGN KEY (tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 FOREIGN KEY (tenant_id,owner_team_id) REFERENCES orbit_business_team(tenant_id,id),
 CONSTRAINT ck_template_revision CHECK (revision BETWEEN 1 AND 9007199254740991),
 CONSTRAINT ck_template_visibility CHECK (visibility IN ('PRIVATE','TEAM')),
 CONSTRAINT ck_template_state CHECK (state IN ('ACTIVE','ARCHIVED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='可复用纯配置模板；共享仅增加模板可读性，不扩展来源权限';

CREATE TABLE orbit_launch_template_recipient (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 template_id CHAR(36) NOT NULL COMMENT '当前共享模板UUID',
 user_id CHAR(36) NOT NULL COMMENT '保存共享时冻结的同团队启用人员UUID，新成员不自动加入',
 PRIMARY KEY (tenant_id,template_id,user_id),
 KEY idx_template_recipient (tenant_id,user_id,template_id) COMMENT '接收者模板列表覆盖索引',
 FOREIGN KEY (tenant_id,template_id) REFERENCES orbit_launch_template(tenant_id,id),
 FOREIGN KEY (tenant_id,user_id) REFERENCES orbit_business_user(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='模板显式共享快照；读取还须当前菜单和团队范围';

CREATE TABLE orbit_launch_template_version (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 template_id CHAR(36) NOT NULL COMMENT '模板稳定UUID',
 revision BIGINT NOT NULL COMMENT '不可变模板配置版本',
 value_json JSON NOT NULL COMMENT '原TemplateWrite及该次真实归属和冻结接收者快照',
 created_at DATETIME(3) NOT NULL COMMENT '版本写入UTC时刻',
 created_by BIGINT NOT NULL COMMENT '实际操作者原若依用户ID',
 PRIMARY KEY (tenant_id,template_id,revision),
 FOREIGN KEY (tenant_id,template_id) REFERENCES orbit_launch_template(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='模板历史版本，加载计划深复制后不受后续修改影响';

CREATE TABLE orbit_launch_name_sequence (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 channel_id CHAR(36) NOT NULL COMMENT '已当前验证渠道UUID，不按显示名作为序列键',
 owner_user_id CHAR(36) NOT NULL COMMENT '实际计划拥有者UUID',
 naming_date DATE NOT NULL COMMENT '项目Asia/Shanghai命名业务日，不是账户时区日',
 last_sequence DECIMAL(30,0) NOT NULL COMMENT '已占用最大序号，不回收；中断允许跳号',
 PRIMARY KEY (tenant_id,channel_id,owner_user_id,naming_date),
 FOREIGN KEY (tenant_id,channel_id) REFERENCES orbit_channel(tenant_id,id),
 FOREIGN KEY (tenant_id,owner_user_id) REFERENCES orbit_business_user(tenant_id,id),
 CONSTRAINT ck_launch_sequence CHECK (last_sequence>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='渠道加投手加项目日期原子占号，不复用已发任务名称';

CREATE TABLE orbit_launch_name_reservation (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 id CHAR(36) NOT NULL COMMENT '命名预留业务UUID',
 plan_id CHAR(36) NOT NULL COMMENT '计划业务UUID',
 plan_revision BIGINT NOT NULL COMMENT '冻结配置版本',
 naming_date DATE NOT NULL COMMENT '项目上海业务日，跨日须重验',
 source_hash CHAR(64) NOT NULL COMMENT '渠道名称及投手昵称全名和配置版本指纹',
 created_at DATETIME(3) NOT NULL COMMENT '占号创建UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_launch_name_plan (tenant_id,plan_id,plan_revision,naming_date,source_hash) COMMENT '同计划版本日期及命名来源重复请求沿用预留，变化允许重新预览',
 FOREIGN KEY (tenant_id,plan_id) REFERENCES orbit_launch_plan(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='不可变系列名称预留，来源或日期变化阻止旧预检提交';

CREATE TABLE orbit_launch_name_item (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 reservation_id CHAR(36) NOT NULL COMMENT '命名预留UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '展开系列稳定排序位置，最多一万',
 slot_key VARCHAR(512) NOT NULL COMMENT '账户UUID及系列local_id及副本序号稳定路径',
 name VARCHAR(200) NOT NULL COMMENT '真实渠道投手项目日期及至少四位序号组合，不截断',
 sequence DECIMAL(30,0) NOT NULL COMMENT '真实已占用序号，API输出数字字符串',
 PRIMARY KEY (tenant_id,reservation_id,ordinal),
 FOREIGN KEY (tenant_id,reservation_id) REFERENCES orbit_launch_name_reservation(tenant_id,id),
 CONSTRAINT ck_launch_name_ordinal CHECK (ordinal BETWEEN 0 AND 9999)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='名称预留有界一万项，冻结后不得因重试改名';

CREATE TABLE orbit_launch_allocation (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 id CHAR(36) NOT NULL COMMENT '真实素材求解分配UUID',
 plan_id CHAR(36) NOT NULL COMMENT '计划业务UUID',
 plan_revision BIGINT NOT NULL COMMENT '求解输入配置版本',
 state VARCHAR(16) NOT NULL COMMENT 'QUEUED、RUNNING、SUCCEEDED或FAILED，未受理不得伪造队列',
 task_id CHAR(36) NULL COMMENT '真实持久异步任务UUID，同步成功可为空',
 algorithm_version VARCHAR(64) NOT NULL COMMENT '当前仅allocation-v1',
 seed INT UNSIGNED NOT NULL COMMENT '稳定边平局种子，零至2147483647',
 input_hash CHAR(64) NOT NULL COMMENT '含完整兼容图及素材版本和权限版本的规范输入摘要',
 warnings_json JSON NOT NULL COMMENT '最多一百项可审查警告，不含凭证',
 active TINYINT NOT NULL COMMENT '当前活跃分配标记，取消保留历史结果',
 created_at DATETIME(3) NOT NULL COMMENT '实际受理UTC时刻',
 updated_at DATETIME(3) NOT NULL COMMENT '状态变更UTC时刻',
 PRIMARY KEY (tenant_id,id),
 UNIQUE KEY uk_launch_allocation_input (tenant_id,plan_id,input_hash) COMMENT '相同完整输入仅一个求解结果',
 KEY idx_launch_allocation_active (tenant_id,plan_id,active,id) COMMENT '当前分配及取消集合有界定位',
 KEY idx_launch_allocation_queue (tenant_id,state,updated_at,id) COMMENT '后台恢复及领取按状态时间键集分页',
 FOREIGN KEY (tenant_id,plan_id) REFERENCES orbit_launch_plan(tenant_id,id),
 CONSTRAINT ck_launch_allocation_state CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
 CONSTRAINT ck_launch_allocation_seed CHECK (seed<=2147483647)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实完整兼容图求解记录，失败不保存部分成功分配';

CREATE TABLE orbit_launch_allocation_item (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 allocation_id CHAR(36) NOT NULL COMMENT '真实分配UUID',
 ordinal INT UNSIGNED NOT NULL COMMENT '完整展开slot稳定排序位置',
 slot_key VARCHAR(512) NOT NULL COMMENT '账户及三层local_id和各自副本编号的完整路径',
 account_id CHAR(36) NOT NULL COMMENT '对应已验证计划账户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '完整匹配选定的真实素材UUID',
 asset_revision BIGINT NOT NULL COMMENT '对应已校验READY及LIVE的真实素材版本',
 asset_sha256 CHAR(64) NOT NULL COMMENT '分配时真实内容摘要，提交前重验',
 PRIMARY KEY (tenant_id,allocation_id,ordinal),
 KEY idx_launch_allocation_asset (tenant_id,asset_id,allocation_id) COMMENT '素材引用审查和失效反向定位',
 FOREIGN KEY (tenant_id,allocation_id) REFERENCES orbit_launch_allocation(tenant_id,id),
 CONSTRAINT ck_launch_allocation_ordinal CHECK (ordinal BETWEEN 0 AND 9999)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='只有整批求解成功才原子写入全部slot，不保留部分分配';

CREATE TABLE orbit_launch_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 actor_id BIGINT NOT NULL COMMENT '实际调用者原若依用户ID，重放仍验当前权限范围',
 operation VARCHAR(48) NOT NULL COMMENT '计划模板动作及稳定资源键的受控作用域',
 key_hash CHAR(64) NOT NULL COMMENT '原幂等键SHA256，不保存客户端原键',
 input_hash CHAR(64) NOT NULL COMMENT '严格归一化请求含CAS版本的规范摘要',
 result_json JSON NOT NULL COMMENT '实际已提交响应快照，无Token；重放先实时复验对象范围',
 created_at DATETIME(3) NOT NULL COMMENT '完成UTC时刻，至少保留两年',
 PRIMARY KEY (tenant_id,actor_id,operation,key_hash),
 KEY idx_launch_idempotency_retention (tenant_id,created_at,key_hash) COMMENT '达到保留期后按时间游标批量清理',
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='计划模板原子幂等结果，失败事务不得留下成功标记';

CREATE TABLE orbit_launch_event (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 id CHAR(36) NOT NULL COMMENT '审计稳定UUID',
 actor_id BIGINT NOT NULL COMMENT '实际操作者原若依用户ID',
 resource_kind VARCHAR(16) NOT NULL COMMENT 'PLAN、TEMPLATE、NAMES或ALLOCATION',
 resource_id CHAR(36) NOT NULL COMMENT '业务资源稳定UUID',
 revision BIGINT NOT NULL COMMENT '动作对应真实版本',
 action VARCHAR(48) NOT NULL COMMENT '受控真实业务动作，不写模拟执行成功',
 request_id CHAR(36) NOT NULL COMMENT '服务端请求追踪UUID',
 details_json JSON NOT NULL COMMENT '脱敏差异及受控原因，不含平台凭证或自由异常正文',
 created_at DATETIME(3) NOT NULL COMMENT 'UTC审计时刻，至少保留两年',
 PRIMARY KEY (tenant_id,id),
 KEY idx_launch_event_resource (tenant_id,resource_kind,resource_id,id) COMMENT '资源历史审计有界查询',
 KEY idx_launch_event_retention (tenant_id,created_at,id) COMMENT '保留期后按时间批量归档',
 FOREIGN KEY (tenant_id) REFERENCES orbit_tenant(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='与配置变更同事务的业务审计，失败应整体回滚';

CREATE TABLE orbit_launch_outbox (
 tenant_id CHAR(36) NOT NULL COMMENT '可信会话租户UUID',
 event_id CHAR(36) NOT NULL COMMENT '对应真实业务审计UUID',
 state VARCHAR(16) NOT NULL COMMENT 'PENDING或DELIVERED，仅内部可靠通知不代表广告已执行',
 created_at DATETIME(3) NOT NULL COMMENT '同事务创建UTC时刻',
 PRIMARY KEY (tenant_id,event_id),
 KEY idx_launch_outbox_pending (state,created_at,tenant_id,event_id) COMMENT '后台有界领取，不扫描配置大JSON',
 FOREIGN KEY (tenant_id,event_id) REFERENCES orbit_launch_event(tenant_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs COMMENT='真实配置事件可靠outbox，与业务及审计同事务';
