package com.adpulse.main.project.wallet;

import com.adpulse.main.project.wallet.ProjectWalletProvider.ProjectWalletContext;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProvisionedWallet;
import com.adpulse.main.safeheron.service.SafeheronWalletService;
import org.springframework.stereotype.Component;

/** 新系统直接调用Safeheron创建项目钱包。 */
@Component
public class DirectSafeheronProjectWalletProvider implements ProjectWalletProvider {
    public static final String MODE = "1";
    private final SafeheronWalletService walletService;

    public DirectSafeheronProjectWalletProvider(SafeheronWalletService walletService) {
        this.walletService = walletService;
    }

    @Override
    public String mode() {
        return MODE;
    }

    @Override
    public ProvisionedWallet provision(ProjectWalletContext context) {
        return new ProvisionedWallet(
                context.projectCode(),
                walletService.createProjectWallet(context.projectCode(), context.projectName()));
    }
}
