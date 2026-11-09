
CREATE TABLE
IF
	NOT EXISTS ad_hourly_summary (
  `date` datetime NULL COMMENT "数据日期",
  `game_platform` varchar(100) NULL COMMENT "游戏平台",
  `ad_platform` varchar(50) NULL COMMENT "投放平台",
  `agent_line` varchar(100) NULL COMMENT "代理线",
  `timezone_name` varchar(100) NULL COMMENT "时区名称",
  `department` varchar(100) NULL COMMENT "部门",
  `china_date` datetime NULL COMMENT "中国时区数据日期",
  `amount_spent` float NULL COMMENT "花费金额",
  `impressions` int NULL COMMENT "展示次数",
  `clicks_all` int NULL COMMENT "点击次数",
  `clicks_unique` int NULL COMMENT "去重点击次数",
  `reach` int NULL COMMENT "覆盖人数",
  `app_installs` int NULL COMMENT "应用安装数",
  `purchases` int NULL COMMENT "购买次数",
  `purchases_value` float NULL COMMENT "购买金额",
  `complete_registration` int NULL COMMENT "完成注册数",
  `subscribe_website` int NULL COMMENT "网站订阅数",
  `subscribe_website_values` float NULL COMMENT "网站订阅价值",
  `lead` int NULL COMMENT "潜在客户数",
  `inline_link_clicks` int NULL COMMENT "链接点击数",
  `unique_inline_link_clicks` int NULL COMMENT "独特链接点击数",
  `bi_registrations` int NULL COMMENT "BI注册人数",
  `bi_first_recharge_amount` float NULL COMMENT "BI首充金额",
  `bi_first_recharge_users` int NULL COMMENT "BI首充人数"
)  ENGINE = OLAP UNIQUE KEY ( `date`, `game_platform`, `ad_platform`, `agent_line`, `timezone_name` ) DISTRIBUTED BY HASH ( `date`,`agent_line` ) BUCKETS AUTO PROPERTIES ( "replication_num" = "1", "enable_unique_key_merge_on_write" = "true", "enable_unique_key_skip_bitmap_column" = "true" );