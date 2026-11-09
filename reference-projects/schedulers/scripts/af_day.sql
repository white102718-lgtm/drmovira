
CREATE TABLE
IF
	NOT EXISTS af_day (
  -- 主键维度
  `date` date NOT NULL COMMENT "安装日期（同期群日期）",
  `level` varchar(30) NOT NULL COMMENT "层级：campaign/adset/ad",
  `media_source` varchar(100) NULL COMMENT "媒体来源",
  `campaign_id` varchar(100) NULL COMMENT "广告系列ID",
  `ad_set_id` varchar(100) NULL COMMENT "广告组ID",
  `ad_id` varchar(100) NULL COMMENT "广告ID",
  `ad_platform` varchar(100) NULL COMMENT "广告平台",

  -- 基础信息
  `campaign_name` varchar(300) NULL COMMENT "广告系列名称",
  `ad_set_name` varchar(300) NULL COMMENT "广告组名称",
  `ad_name` varchar(300) NULL COMMENT "广告名称",
  `platform` varchar(50) NULL COMMENT "平台：iOS/Android",

  -- 安装基础指标
  `installs` INT NULL COMMENT "总安装数",

  -- 注册/充值指标（D0当天）
  `register_users` INT NULL COMMENT "注册用户数",
  `first_recharge_users` INT NULL COMMENT "首充总人数（复购留存的分母）",
  `same_day_register_first_recharge_users` INT NULL COMMENT "当日注册首充用户数",

  -- D1~D30 复购人数（用于计算复购留存率 = dN_purchase_users / first_recharge_users）
  `d1_purchase_users` INT NULL COMMENT "D1复购人数",
  `d2_purchase_users` INT NULL COMMENT "D2复购人数",
  `d3_purchase_users` INT NULL COMMENT "D3复购人数",
  `d4_purchase_users` INT NULL COMMENT "D4复购人数",
  `d5_purchase_users` INT NULL COMMENT "D5复购人数",
  `d6_purchase_users` INT NULL COMMENT "D6复购人数",
  `d7_purchase_users` INT NULL COMMENT "D7复购人数",
  `d8_purchase_users` INT NULL COMMENT "D8复购人数",
  `d9_purchase_users` INT NULL COMMENT "D9复购人数",
  `d10_purchase_users` INT NULL COMMENT "D10复购人数",
  `d11_purchase_users` INT NULL COMMENT "D11复购人数",
  `d12_purchase_users` INT NULL COMMENT "D12复购人数",
  `d13_purchase_users` INT NULL COMMENT "D13复购人数",
  `d14_purchase_users` INT NULL COMMENT "D14复购人数",
  `d15_purchase_users` INT NULL COMMENT "D15复购人数",
  `d16_purchase_users` INT NULL COMMENT "D16复购人数",
  `d17_purchase_users` INT NULL COMMENT "D17复购人数",
  `d18_purchase_users` INT NULL COMMENT "D18复购人数",
  `d19_purchase_users` INT NULL COMMENT "D19复购人数",
  `d20_purchase_users` INT NULL COMMENT "D20复购人数",
  `d21_purchase_users` INT NULL COMMENT "D21复购人数",
  `d22_purchase_users` INT NULL COMMENT "D22复购人数",
  `d23_purchase_users` INT NULL COMMENT "D23复购人数",
  `d24_purchase_users` INT NULL COMMENT "D24复购人数",
  `d25_purchase_users` INT NULL COMMENT "D25复购人数",
  `d26_purchase_users` INT NULL COMMENT "D26复购人数",
  `d27_purchase_users` INT NULL COMMENT "D27复购人数",
  `d28_purchase_users` INT NULL COMMENT "D28复购人数",
  `d29_purchase_users` INT NULL COMMENT "D29复购人数",
  `d30_purchase_users` INT NULL COMMENT "D30复购人数",
) UNIQUE KEY (`date`, `level`, `media_source`, `campaign_id`, `ad_set_id`, `ad_id`)
DISTRIBUTED BY HASH(`ad_id`)
BUCKETS AUTO
PROPERTIES ("replication_num" = "1");
