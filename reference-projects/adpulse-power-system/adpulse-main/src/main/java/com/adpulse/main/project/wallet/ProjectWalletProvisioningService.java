package com.adpulse.main.project.wallet;

import com.adpulse.main.project.dto.ProjectViews.ProjectWallet;
import com.adpulse.main.project.mapper.ProjectMapper;
import com.adpulse.main.project.model.Project;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProjectWalletContext;
import com.adpulse.main.project.wallet.ProjectWalletProvider.ProvisionedWallet;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

/** 根据字典选择钱包供应方，并在钱包完整落库后关联项目。 */
@Service
public class ProjectWalletProvisioningService {
    private static final String DICT_CODE = "PROJECT_CREATE_WALLET";
    private static final List<String> SUPPORTED_MODES = List.of("0", "1");
    private final ProjectMapper mapper;
    private final Map<String, ProjectWalletProvider> providers;

    public ProjectWalletProvisioningService(
            ProjectMapper mapper, List<ProjectWalletProvider> providers) {
        this.mapper = mapper;
        this.providers =
                providers.stream()
                        .collect(
                                Collectors.toUnmodifiableMap(
                                        ProjectWalletProvider::mode, Function.identity()));
    }

    /** 创建或同步项目钱包；配置缺失和重复配置都拒绝猜测供应方。 */
    public ProjectWallet provision(ProjectWalletContext context) {
        String mode = resolveMode();
        ProjectWalletProvider provider = providers.get(mode);
        if (provider == null) {
            throw new ProjectWalletProvisioningException("钱包创建方式未安装对应实现：" + mode);
        }
        ProvisionedWallet provisioned;
        try {
            provisioned = provider.provision(context);
        } catch (ProjectWalletProvisioningException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ProjectWalletProvisioningException(
                    blank(exception.getMessage()) ? "钱包创建失败，请稍后重试" : exception.getMessage(),
                    exception);
        }
        if (provisioned == null
                || blank(provisioned.customerRefId())
                || provisioned.wallet() == null) {
            throw new ProjectWalletProvisioningException("钱包创建结果不完整");
        }
        if (mapper.updateWalletCustomerRefId(context.projectId(), provisioned.customerRefId()) != 1) {
            Project current = mapper.findProject(context.projectId());
            if (current == null
                    || !provisioned.customerRefId().equals(current.getWalletCustomerRefId())) {
                throw new ProjectWalletProvisioningException("项目已关联其他钱包，请刷新后重试");
            }
        }
        return provisioned.wallet();
    }

    private String resolveMode() {
        List<String> enabled =
                SUPPORTED_MODES.stream()
                        .filter(value -> mapper.countEnabledDictionaryValue(DICT_CODE, value) == 1)
                        .toList();
        if (enabled.size() != 1) {
            throw new ProjectWalletProvisioningException(
                    "钱包创建方式配置异常，请确保字典PROJECT_CREATE_WALLET仅启用一个0或1值");
        }
        return enabled.getFirst();
    }

    private boolean blank(String value) {
        return value == null || value.isBlank();
    }

    /** 项目钱包供应失败；消息可安全展示，不包含外部凭证或完整响应。 */
    public static class ProjectWalletProvisioningException extends RuntimeException {
        public ProjectWalletProvisioningException(String message) {
            super(message);
        }

        public ProjectWalletProvisioningException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
