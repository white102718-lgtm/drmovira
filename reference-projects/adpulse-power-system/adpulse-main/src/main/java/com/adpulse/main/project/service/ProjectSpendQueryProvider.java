package com.adpulse.main.project.service;

import java.math.BigDecimal;

/** 项目累计广告消耗查询。 */
public interface ProjectSpendQueryProvider {
    /** 按项目名称精确匹配广告平台，汇总全历史 USD 消耗。 */
    BigDecimal totalSpend(String projectName);
}
