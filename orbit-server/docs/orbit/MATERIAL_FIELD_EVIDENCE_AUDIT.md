# 素材小批字段证据审计

审计时间：2026-11-08。只读核对docs/orbit/progress.json现2342项、FIELD_MATRIX.md及MODULE_LOGIC AST-01/03/06/09。未修改总台账。本表只挑响应字段，不把字段Schema通过扩大为上传、杀毒、业务READY、历史追踪或整个素材模块通过。

## 当前可结清性

下列6项是可小范围复验的候选，当前不能直接勾选当前源码验收。最新包含全部原Asset/Tag/Category Schema三组的真实PASS为python-material-runtime-full-browser.json（2026-11-08T09:10:17.373429Z，92/92，实际六UI）。但只读SHA256比对发现material_store.py、material_library.py、material_routes.py、material_worker.py、tools/material_checks.py、material_video_checks.py与该回执已不同；material_contract.py、material_antivirus_sql.py及material_schema_checks.py相同。故该回执是历史真实通过，不覆盖当前完整受测链。此次审计没有运行任何服务、SQL或扫描。

## 精确候选映射

| ledger ID | 原字段约束与当前实现 | 具名实际历史case / 回执 | 独立结论与仍缺边界 |
| --- | --- | --- | --- |
| SCHEMA-Asset.id | 原Asset必填UUID；material_store.public_asset直接返回持久id；material_routes按UUID解析，create_session服务端生成id | pythonMaterialOriginalAssetSchemaTypesAndDecimalDuration；pythonMaterialActualPngUploadProcessingAndAuthenticatedPreview；pythonMaterialTaxonomyOriginalFieldsAndFixedUncategorized（非法UUID422） / runtime-full-browser | 可独立验证标识格式、上传会话→GET同id与非法ID拒绝。当前SHA漂移须复验；不因此证明整个资产对象所有权/历史业务 |
| SCHEMA-Tag.id | 原Tag必填UUID；taxonomy创建生成UUID、GET按同tenant+kind+id查；material_library.taxonomy_get与taxonomy_save | pythonMaterialOriginalTagSchemaAndRegisteredVisibleCountExtension；pythonMaterialTaxonomyOriginalFieldsAndFixedUncategorized（create→GET原字段逐值相等） / 同回执 | UUID及读写身份可独立结清，当前链需复验；不包含标签停用全部行为或引用数扩展 |
| SCHEMA-Category.id | 原Category必填UUID；同上CATEGORY条件，与TAG隔离 | pythonMaterialOriginalCategorySchemaAndRegisteredVisibleCountExtension；pythonMaterialTaxonomyOriginalFieldsAndFixedUncategorized（固定未分类与新分类GET） / 同回执 | UUID与GET身份可独立结清，当前链需复验；不包含固定分类所有保护/归档竞争 |
| SCHEMA-Asset.kind | 原枚举IMAGE/VIDEO；material_contract.MIME_KIND仅JPEG/PNG→IMAGE、MP4→VIDEO，store创建写持久kind，public_asset返回原kind | pythonMaterialOriginalAssetSchemaTypesAndDecimalDuration；pythonMaterialActualMp4HttpWorkerDurationAndAuthenticatedPreview（kind==VIDEO）；pythonMaterialUploadStrictFieldsHashAndPartConflict / 同回执 | 图片/视频实际分支加原Schema枚举候选。当前链需复验；平台能力兼容、完整所有MIME攻击与READY全流程不能由此推断 |
| SCHEMA-Asset.sha256 | 原必填64字符；parse_material散列规范与store.complete大小/hash复验；public_asset返回持久原文件散列 | pythonMaterialUploadStrictFieldsHashAndPartConflict（实际分片etag与sha256、冲突拒绝）；pythonMaterialOriginalAssetSchemaTypesAndDecimalDuration；pythonMaterialActualMp4HttpWorkerDurationAndAuthenticatedPreview / 同回执 | 可验证原字段长度与真实文件散列链；需当前源码复验。Schema本身只约束64字符，不等于已证明所有文件/整个AV来源绑定 |
| SCHEMA-Asset.duration_seconds | 原decimal字符串最多6小数/28字符或null；store.public_asset对DECIMAL固定f格式，图片null，处理Worker持久真实媒体时长 | pythonMaterialOriginalAssetSchemaTypesAndDecimalDuration；pythonMaterialActualPngUploadProcessingAndAuthenticatedPreview（null）；pythonMaterialActualMp4HttpWorkerDurationAndAuthenticatedPreview（真实2.000000）；pythonMaterialTruncatedMp4WorkerNeverPublishesReady（null） / 同回执 | 有真实字符串与null两分支候选；当前链需复验。不能据2秒样本宣称所有最大时长/精度/超长视频边界通过 |

原Schema读取器tools/material_schema_checks.py:validate_original_schema直接加载data原openapi-current.json，不用产品自己的DTO代替合同；原Asset.additionalProperties=false明确不把宽高加入Asset。Tag/Category技术扩展visible_asset_count先严格拆出单一字段，原字段仍逐项校验，不能泛化忽略未知额外字段。

## 本批不建议勾选的字段

Asset.state/preview_url：虽然真实PNG、MP4、感染内存、legacy安全门禁及六UI已有分项通过，但状态是完整上传/扫描/处理/归档生命周期，不能以单一Schema枚举或READY样本结清。

Asset.revision及Tag/Category.revision：已有过期409与递增真实分支，但穷尽MAX_REVISION、重复幂等不增版本等合同边界仍要单独审查，不能把integer范围读取当业务CAS完成。

Tag/Category.name、Tag.group：已有真实创建/分组保留及同类唯一性专项，但当前读取样本不能替代0/30/31码点、NFC/trim/控制字符所有边界；不据Schema验证直接关闭基础字段name等更大逻辑条目。Asset.category_id/tag_ids关联启停/保留与选择权限也保持独立待审。

## 主线最小复验建议

复用既有共享runner，至少through038、material-only、include-materials、include-material-taxonomy、include-material-video，加主线已校验固定scanner manifest与video工具参数（不另造环境/路径）。保持原12素材+5媒体+2迁移+5查询+3原Schema具名检查，不需要为这6个只读响应候选重复六UI/500MiB/生命周期整套。实际命令和固定参数由主线按当前runner填写并串行运行；新回执必须包含当前关键生产源/tool SHA与全部具名case，成功后才由主线决定这6个精确schema ledger项状态。若只跑列表Schema不含真实MP4，则duration/kind不能合并结清。


## 当前限定复验结果（2026-11-08 21:38，北京时间）

主线已在through039隔离MySQL/Redis/HTTP重执行42/42，通过真实PNG、真实MP4、截断视频、扫描状态、标签分类以及原Asset/Tag/Category Schema链。实际回执为evidence/python-material-original-field-current-http.json；8个已执行具名检查的限定映射为evidence/python-material-original-field-types.json，依赖源码与父回执一致。上述6个精确Schema字段现已登记开发DONE、测试PASS；acceptance仍NOT_RUN，不把字段响应类型证据扩大到整个素材模块、所有容量或外部平台。原历史漂移说明保留，用于解释为何必须重验。
