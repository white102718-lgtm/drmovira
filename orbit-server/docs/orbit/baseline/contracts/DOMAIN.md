# 本版范围适用说明

本文为原合同详细语义基线。已删除的独立模块流程不再实施，适用边界以01_修订需求与删除边界.md为准；保留页面的字段、AI闭环、预算、状态与双通道规则不因此删除。

# 领域模型及迁移交付合同

所有普通业务表带tenant_id、内部UUID、created_at/updated_at；可变表带revision≥1。租户内外键包含tenant_id，数据库应用角色不拥有表且无BYPASSRLS。引用必须验证同账户/团队和业务层级。历史表只追加，纠错用新版本。

## 迁移分组

|组|必须交付表|关键约束及索引|
|---|---|---|
|M01 身份|tenants、users、teams、memberships、roles、role_permissions、role_menus、user_roles、managed_teams、sessions、invitations|用户数据角色；每用户一个当前团队；菜单/动作独立；身份sub唯一；session可撤销；超级管理员可跨租户，范围由服务端计算|
|M02 所有权|resource_user_owners、resource_recipients、scope_versions|主数据多个同团队拥有者；模板冻结接收人；tenant+resource_kind+resource_id+user唯一；变更递增scope_version|
|M03 资产授权|ad_accounts、account_assignments、account_grants、integrations、integration_assets、entity_versions、entities|tenant+external_id唯一；分配按业务日区间禁止重叠；实体父级同账户且只能上一级；预算拥有者显式保存；凭据仅secret_ref|
|M04 主数据|clients、products、business_agents、product_agents、channels、app_packages、package_channels、package_accounts、vendors|总代business_agents与执行机器execution_agents绝不混用；包渠道同产品；渠道只能选product_agents成员；vendor状态ENABLED/DISABLED；费率0—100、两位小数|
|M05 归属|vendor_account_bindings、vendor_account_history、ad_channel_bindings、attribution_corrections、attribution_versions、vendor_balance_observations|当前每账户至多一个户商；历史[start,end)；更正双人审批；余额观测带currency/kind/source/evidence，不靠回执相加|
|M06 计划|launch_plans、plan_versions、plan_nodes、plan_identity_bindings、plan_allocations、allocation_items、campaign_name_sequences、campaign_name_reservations、plan_channel_snapshots|plan内local_id唯一；冻结版本不可改；reservation按tenant+plan+revision+展开key唯一；序号按tenant+channel+actor+命名日原子占用；plan+revision唯一task|
|M07 素材模板|assets、asset_versions、asset_uploads、asset_upload_parts、asset_links、asset_task_refs、tags、categories、asset_tags、templates、template_versions|对象路径服务端分配；上传part唯一；物理hash去重不泄露跨所有者信息；活跃引用阻止批删；模板版本追加|
|M08 指标采集|metric_profiles、sync_batches、fact_manifests、published_snapshots、query_snapshots、export_jobs|profile版本冻结；所有分页齐全后publish；generation单调；过期旧响应不能覆盖新值；scope_version参与查询快照|
|M09 规则分析|rules、rule_versions、rule_scopes、rule_runs、rule_hits、analysis_jobs、analysis_evidence、suggestions、suggestion_versions、analysis_limits|run按rule+revision+slot唯一；hit去重；冷却与额度事务检查；analysis_generation防晚到覆盖；费用账本预占和核销|
|M10 执行|tasks、task_nodes、task_dependencies、commands、command_attempts、submission_groups、suggestion_commands、budget_ledger、budget_reservations|command tenant+幂等键唯一；payload hash冲突409；节点成功不重建；对象锁+fencing；共享预算共用额度锁；UNKNOWN保留预占|
|M11 环境|execution_agents、profiles、account_profile_bindings、profile_leases、heartbeats、workflow_versions、adapter_capabilities、agent_events、reconciliation_cases、reconciliation_reviews|Profile按tenant+agent+external_profile唯一；租约原子续期；boot_id+seq去重；操作event_id幂等；Agent证书可撤销；人工复核双人|
|M12 审批|resource_requests、request_versions、request_decisions、fulfillment_receipts、fulfillment_items、request_verifications|vendor+receipt_ref唯一，相同payload幂等；申请/审批/履约/核验职责隔离；外部账户集合去重；允许部分履约终态|
|M13 保障|outbox、inbox、audit_events、alerts、alert_receipts、kill_switches、release_manifests|inbox consumer+event唯一；outbox持久重发；审计只追加；提醒已读按用户；停写开关不停止核验|

每个迁移组必须含：建表和索引、所有租户表FORCE RLS、跨租户FK检查、升级兼容说明、回退策略、空库及升级测试。reference_sql是v1.1示例经总代消歧后的参考，不是待直接执行的全量迁移；不得把示例注释当已落地策略。

## ClickHouse事实和授权

fact_versions粒度tenant/account/entity_type/entity_id/business_date/metric_profile_id/breakdown_key；追加source_version、batch_id、observed_at、quality、is_deleted、currency、冻结operator_user_id/owner_team_id/channel_id/product_snapshot/attribution_version。逻辑版本必须在同一粒度单调；报表先argMax完整tuple再过滤删除，再汇总。原始100、新120、迟到旧110结果为120。

聚合表至少account_daily、operator_daily、channel_daily、asset_daily、launch_cohort_daily、rule_metric_snapshot。每张预聚合保留tenant+owner_team+operator+profile+currency+business_date及可加分子分母，不能只按tenant/day聚合后向一般用户返回。相同channel跨多个用户的统计须先按所有权过滤再聚合。渠道和投手日期筛选均为账户当地同名业务日。

冻结事实历史归属，不使用当前owner直接join改写历史。后台更正以新attribution_version重算，发布新的snapshot；导出保留原query_snapshot_id及校验hash。用户撤权使下载不可用，不改变历史数值。

## 服务边界

采用模块化单体API与独立Worker。事务模块为身份、业务主数据、计划素材、规则分析、执行审批；指标查询通过单一授权查询服务访问ClickHouse。API及Worker只通过相应模块接口写入，禁止绕开command服务直接调用平台写接口。

MCP/浏览器执行器是Adapter，不能拥有与command服务不同的状态机。AI Adapter不能获得平台执行凭据。Redis只缓存和短期协调，所有不可丢状态在PostgreSQL/持久队列及Agent本地spool。
