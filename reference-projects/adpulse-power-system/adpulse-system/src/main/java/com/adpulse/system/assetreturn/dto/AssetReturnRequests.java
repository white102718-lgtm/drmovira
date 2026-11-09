package com.adpulse.system.assetreturn.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 资产回收接口请求对象。 */
public final class AssetReturnRequests {

    private AssetReturnRequests() {}

    /**
     * 发起回收请求。
     *
     * @param reason 回收原因
     */
    public record Create(
            @NotBlank(message = "请填写回收原因") @Size(max = 1000, message = "回收原因不能超过1000个字") String reason) {}

    /**
     * 完成回收请求。
     *
     * @param outcome 回收结果：AVAILABLE 重新入库，DISABLED 停用
     */
    public record Complete(@NotBlank(message = "请选择回收结果") String outcome) {}
}
