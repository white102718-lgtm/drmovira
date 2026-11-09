-- 素材独立业务表。仅显式迁移；不创建目录、不启动处理任务、不访问云存储。
CREATE TABLE orbit_material_clock (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '素材目录水位；变更使旧游标失效',
 PRIMARY KEY(tenant_id)
) COMMENT='素材目录一致性水位';

CREATE TABLE orbit_material_taxonomy (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 id CHAR(36) NOT NULL COMMENT '分类或标签UUID',
 kind VARCHAR(8) NOT NULL COMMENT 'CATEGORY分类或TAG标签',
 name VARCHAR(30) NOT NULL COMMENT 'NFC显示名称',
 group_name VARCHAR(30) NOT NULL DEFAULT '' COMMENT '标签分组；分类为空',
 state VARCHAR(8) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED启用或DISABLED停用',
 is_system TINYINT NOT NULL DEFAULT 0 COMMENT '系统未分类项不可停用',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '乐观锁版本',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '登记UTC时间',
 PRIMARY KEY(tenant_id,id),
 UNIQUE KEY uq_material_taxonomy_name(tenant_id,kind,group_name,name) COMMENT '租户内同组同类型名称唯一',
 KEY idx_material_taxonomy_page(tenant_id,kind,state,id) COMMENT '启停状态与UUID键集续页'
) COMMENT='素材标签分类目录';

CREATE TABLE orbit_material_asset (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 id CHAR(36) NOT NULL COMMENT '素材UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '真实业务拥有者UUID',
 owner_team_id CHAR(36) NOT NULL COMMENT '真实拥有者团队UUID',
 name VARCHAR(100) NOT NULL COMMENT '业务素材名；不能用作文件路径',
 category_id CHAR(36) NOT NULL COMMENT '当前分类UUID',
 kind VARCHAR(5) NOT NULL COMMENT 'IMAGE图片或VIDEO视频',
 mime VARCHAR(20) NOT NULL COMMENT '声明并经服务端核验的MIME',
 state VARCHAR(24) NOT NULL COMMENT '上传、扫描、处理、可用或归档状态',
 sha256 CHAR(64) NOT NULL COMMENT '小写文件SHA256；跨拥有者不返回重复信息',
 byte_size BIGINT NOT NULL COMMENT '原始文件字节数；图片20MiB视频500MiB上限',
 object_upload_id CHAR(36) NOT NULL COMMENT '内部对象上传UUID；不对外返回物理路径',
 duration_seconds DECIMAL(20,6) NULL COMMENT '视频真实时长秒；未处理为NULL',
 width_px INT NULL COMMENT '服务端解码宽度',
 height_px INT NULL COMMENT '服务端解码高度',
 preview_ready TINYINT NOT NULL DEFAULT 0 COMMENT '已生成安全预览，不表示云存储已验收',
 error_code VARCHAR(40) NULL COMMENT '不含路径或秘密的处理失败代码',
 revision BIGINT NOT NULL DEFAULT 1 COMMENT '素材乐观锁版本',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '创建UTC时间',
 updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '修改UTC时间',
 archived_at DATETIME(3) NULL COMMENT '逻辑归档UTC时间；物理文件最短保留30日',
 PRIMARY KEY(tenant_id,id),
 KEY idx_material_owner_page(tenant_id,owner_user_id,state,id) COMMENT '一般用户拥有者状态分页',
 KEY idx_material_team_page(tenant_id,owner_team_id,state,id) COMMENT '团队管理员范围分页',
 KEY idx_material_category_page(tenant_id,category_id,state,id) COMMENT '分类筛选键集续页',
 KEY idx_material_name_page(tenant_id,name,id) COMMENT '按名称排序；UUID稳定次序',
 KEY idx_material_dedup(tenant_id,owner_user_id,sha256,state) COMMENT '仅同拥有者READY素材去重'
) COMMENT='素材元数据；事实指标单独聚合，未知值不可填零';

CREATE TABLE orbit_material_asset_tag (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '素材UUID',
 tag_id CHAR(36) NOT NULL COMMENT '标签UUID；停用后保留已有关系',
 PRIMARY KEY(tenant_id,asset_id,tag_id),
 KEY idx_material_tag_assets(tenant_id,tag_id,asset_id) COMMENT 'ANY和ALL标签倒排过滤'
) COMMENT='素材标签关系';

CREATE TABLE orbit_material_upload (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 id CHAR(36) NOT NULL COMMENT '上传会话UUID',
 asset_id CHAR(36) NOT NULL COMMENT '素材UUID',
 owner_user_id CHAR(36) NOT NULL COMMENT '创建者业务UUID',
 expires_at DATETIME(3) NOT NULL COMMENT '上传24小时失效时刻',
 state VARCHAR(24) NOT NULL COMMENT 'INITIATED或UPLOADING或COMPLETE或EXPIRED',
 PRIMARY KEY(tenant_id,id),
 KEY idx_material_asset_upload(tenant_id,asset_id) COMMENT '同拥有者去重可返回已有素材的会话',
 KEY idx_material_upload_expiry(state,expires_at,tenant_id,id) COMMENT '有界过期回收任务'
) COMMENT='素材分片上传会话';

CREATE TABLE orbit_material_upload_part (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 upload_id CHAR(36) NOT NULL COMMENT '上传会话UUID',
 part_number INT NOT NULL COMMENT '从1开始的8MiB分片编号',
 byte_size INT NOT NULL COMMENT '真实分片字节数',
 etag CHAR(64) NOT NULL COMMENT '服务端真实SHA256分片摘要',
 PRIMARY KEY(tenant_id,upload_id,part_number)
) COMMENT='已确认上传分片；相同编号不同内容拒绝';

CREATE TABLE orbit_material_reference (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '素材UUID',
 id CHAR(36) NOT NULL COMMENT '引用关系UUID',
 kind VARCHAR(24) NOT NULL COMMENT 'ALLOCATION或EXECUTION或HISTORICAL_EVIDENCE',
 resource_id CHAR(36) NOT NULL COMMENT '分配或执行等业务UUID',
 active TINYINT NOT NULL COMMENT '活跃分配和执行阻止归档；历史证据只阻止物理清理',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '引用登记UTC时间',
 PRIMARY KEY(tenant_id,asset_id,id),
 UNIQUE KEY uq_material_reference(tenant_id,asset_id,kind,resource_id) COMMENT '引用登记幂等'
) COMMENT='素材引用锁；写方必须先锁同素材行';

CREATE TABLE orbit_material_job (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 asset_id CHAR(36) NOT NULL COMMENT '素材UUID',
 actor_id BIGINT NOT NULL COMMENT '提交处理任务的真实登录主体；非Worker身份',
 actor_auth_version BIGINT NOT NULL COMMENT '提交时发起人授权版本；撤权不复活旧任务',
 scope_digest CHAR(64) NOT NULL COMMENT '发起身份及素材相关范围摘要；不绑定无关目录水位',
 state VARCHAR(12) NOT NULL COMMENT 'PENDING或RUNNING或DONE或FAILED',
 claim_id CHAR(36) NULL COMMENT '持久处理租约UUID',
 claimed_at DATETIME(3) NULL COMMENT '领取UTC时刻；超时不能假定处理成功',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '入队UTC时间',
 PRIMARY KEY(tenant_id,asset_id),
 KEY idx_material_job_claim(state,created_at,tenant_id,asset_id) COMMENT 'SKIP LOCKED有界处理领取'
) COMMENT='扫描及衍生处理持久任务';

CREATE TABLE orbit_material_idempotency (
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 actor_id BIGINT NOT NULL COMMENT '真实登录主体',
 request_key VARCHAR(128) NOT NULL COMMENT '客户端单次意图幂等键',
 payload_hash CHAR(64) NOT NULL COMMENT '规范业务请求摘要含动作与版本',
 response_json JSON NOT NULL COMMENT '已提交业务响应；不含文件或临时凭据',
 PRIMARY KEY(tenant_id,actor_id,request_key)
) COMMENT='素材事务幂等结果';

CREATE TABLE orbit_material_audit (
 id CHAR(36) NOT NULL COMMENT '事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 actor_id BIGINT NOT NULL COMMENT '真实操作用户；0表示本地系统Worker',
 action VARCHAR(40) NOT NULL COMMENT '素材或分类标签动作',
 resource_id CHAR(36) NOT NULL COMMENT '业务资源UUID',
 revision BIGINT NOT NULL COMMENT '提交后版本',
 request_id CHAR(36) NOT NULL COMMENT '请求关联UUID',
 change_json JSON NOT NULL COMMENT '必要字段前后差异和实际原因；不含文件正文或凭据',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '事件UTC时间',
 PRIMARY KEY(id),
 KEY idx_material_audit_scope(tenant_id,created_at,id) COMMENT '租户事件时间续页'
) COMMENT='素材不含文件正文的原子审计';

CREATE TABLE orbit_material_outbox (
 event_id CHAR(36) NOT NULL COMMENT '与审计相同的去重事件UUID',
 tenant_id CHAR(36) NOT NULL COMMENT '租户UUID',
 resource_id CHAR(36) NOT NULL COMMENT '素材或目录UUID',
 revision BIGINT NOT NULL COMMENT '已提交版本',
 created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)) COMMENT '事件UTC时间',
 PRIMARY KEY(event_id),
 KEY idx_material_outbox_time(created_at,event_id) COMMENT '有界消费者续页'
) COMMENT='素材与业务同事务outbox';

-- 初始化现有租户。新租户创建流程也须在同事务插入水位与系统分类。
INSERT INTO orbit_material_clock(tenant_id,revision)
 SELECT id,1 FROM orbit_tenant;
INSERT INTO orbit_material_taxonomy(tenant_id,id,kind,name,group_name,state,is_system,revision)
 SELECT id,'00000000-0000-4000-8000-000000000001','CATEGORY','未分类','','ENABLED',1,1
 FROM orbit_tenant;
