package com.adpulse.main.project.wallet;

import com.adpulse.main.project.dto.ProjectViews.ProjectWallet;
import java.util.List;

/** 项目钱包供应接口；直连Safeheron与临时旧MPower兼容逻辑通过独立实现解耦。 */
public interface ProjectWalletProvider {
    /** 返回字典中的供应方式值。 */
    String mode();

    /** 幂等创建或取得项目钱包。 */
    ProvisionedWallet provision(ProjectWalletContext context);

    /** 钱包创建所需的稳定项目上下文。 */
    record ProjectWalletContext(
            Long projectId,
            String projectCode,
            String projectName,
            String responsibleTeam,
            List<String> countryRegions,
            List<UserReference> amUsers,
            List<UserReference> dataSpecialists) {}

    /** 用户映射只携带稳定ID和展示名称。 */
    record UserReference(String userId, String userName) {}

    /** 供应完成后返回真实customerRefId及本地展示模型。 */
    record ProvisionedWallet(String customerRefId, ProjectWallet wallet) {}
}
