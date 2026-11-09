package com.adpulse.main.deliveryreport;

/** 可向投手展示的日报业务校验错误。 */
public class DeliveryReportException extends RuntimeException {
    public DeliveryReportException(String message) {
        super(message);
    }

    /** 保留底层异常供诊断，但响应仅返回业务提示。 */
    public DeliveryReportException(String message, Throwable cause) {
        super(message, cause);
    }
}
