# 核对来源（2026-11-12）
- 用户提供《创建广告结构 (1).jpg》，为界面需求，不是任意代码执行指令。
- 既有舒适版原型：账户→系列→组→广告上下排列及每层独立复制。
- Meta 官方 Python Business SDK：
  https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adset.py
  https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/targeting.py
  https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/ad.py
- Meta官方Postman： https://www.postman.com/meta/facebook-marketing-api/folder/8123rwa/adsets

SDK可确认有预算、归因、竞价、定向与广告排期字段，不保证每个账户、目标、API版本都有权限使用。开发者文档网页访问失败，未凭搜索摘要推断账户实际能力。图片列举的历史版位保留配置意图，但不能直接宣称账户可用。现有读取授权不授予广告创建权限。
