package com.adpulse.main.deliveryreport;

import com.adpulse.main.deliveryreport.DeliveryReportTypes.PlatformRow;
import java.time.LocalDate;
import java.util.List;

/** 仅按服务端当前用户英文名称读取当天 campaign 事实。 */
public interface DeliveryReportQueryProvider {
    List<PlatformRow> query(LocalDate date, String placerId);

    /** 日期闭区间内按投放师集合一次查询平台消耗。 */
    List<com.adpulse.main.deliveryreport.DeliveryReportTypes.SpendRow> querySpend(
            LocalDate startDate, LocalDate endDate, List<String> placerIds);
}
