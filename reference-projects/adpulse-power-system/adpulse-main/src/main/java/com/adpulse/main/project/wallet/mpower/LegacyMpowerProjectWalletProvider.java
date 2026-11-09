package com.adpulse.main.project.wallet.mpower;

import com.adpulse.main.project.wallet.ProjectWalletProvider;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProjectWalletContext;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProvisionedWallet;
import com.adpulse.main.project.wallet.mpower.LegacyMpowerFieldMappingResolver.LegacyProjectFields;
import com.adpulse.main.project.wallet.mpower.MpowerWalletClient.EnsureWalletRequest;
import com.adpulse.main.project.wallet.mpower.MpowerWalletClient.WalletData;
import com.adpulse.main.safeheron.service.SafeheronWalletService;
import com.adpulse.main.safeheron.service.SafeheronWalletService.ImportedCoin;
import com.adpulse.main.safeheron.service.SafeheronWalletService.ImportedWallet;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Component;

/** 临时通过旧MPower创建钱包；所有旧字段转换均封装在该适配器内。 */
@Component
public class LegacyMpowerProjectWalletProvider implements ProjectWalletProvider {
    public static final String MODE = "0";
    private final MpowerWalletClient client;
    private final MpowerWalletProperties properties;
    private final LegacyMpowerFieldMappingResolver fieldMappingResolver;
    private final SafeheronWalletService walletService;

    public LegacyMpowerProjectWalletProvider(
            MpowerWalletClient client,
            MpowerWalletProperties properties,
            LegacyMpowerFieldMappingResolver fieldMappingResolver,
            SafeheronWalletService walletService) {
        this.client = client;
        this.properties = properties;
        this.fieldMappingResolver = fieldMappingResolver;
        this.walletService = walletService;
    }

    @Override
    public String mode() {
        return MODE;
    }

    @Override
    public ProvisionedWallet provision(ProjectWalletContext context) {
        LegacyProjectFields fields = fieldMappingResolver.resolve(context);
        WalletData data =
                client.ensureProjectWallet(
                        new EnsureWalletRequest(
                                "ad-mpower-project-" + context.projectId(),
                                context.projectCode(),
                                context.projectName(),
                                properties.getDefaultTenantId(),
                                fields.liabilityCompany(),
                                fields.region(),
                                0L,
                                fields.am(),
                                fields.dataSpecialist()));
        ImportedWallet imported =
                new ImportedWallet(
                        data.accountKey(),
                        data.accountName(),
                        data.customerRefId(),
                        data.teamId(),
                        data.coins() == null
                                ? List.of()
                                : data.coins().stream()
                                        .filter(Objects::nonNull)
                                        .map(
                                                coin ->
                                                        new ImportedCoin(
                                                                coin.coinKey(),
                                                                coin.coinName(),
                                                                coin.feeUnit(),
                                                                coin.address()))
                                        .toList());
        return new ProvisionedWallet(
                data.customerRefId(), walletService.importProjectWallet(imported));
    }
}
