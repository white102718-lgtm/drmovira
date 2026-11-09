# 规则编辑定义专属SDK

`src/api/orbit/rule-editor-definition.ts`仅调用`GET /api/v1/rules/{id}/edit-definition`。它沿当前`rules.edit`及规则可见性，不借用通用`rules.read`或账户/指标管理动作。

响应严格为`rule`原15字段与`stored_scope`四字段。后者只有原scope ID、真实sealed成员数及当前规则owner/team；必须与Rule中的ID/归属一致，数量1—50000。它是已保存历史元数据，不是Scope5，不增加hash、created_at或当前可用证明。原profile停用不影响读取完整规则定义。

SDK逐项解析原Rule，拒绝额外键、错对象、错归属及伪造数量。请求固定GET/no-store，处理认证epoch、取消、15秒客户端期限、2MiB读取上限与原错误字段；不自动重试或将503转为空定义。此客户端期限不替代后端容量标准。

专属8项协议纯测覆盖完整形状、错绑定、请求ID、403/409/503与认证迟到。fetch替身仅验证客户端边界，真实HTTP/当前权限由主线专项另验。
