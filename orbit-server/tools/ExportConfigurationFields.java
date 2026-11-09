import com.ruoyi.system.orbit.config.ConfigurationCatalog;

/** 导出实际Java字段目录供台账使用；只含规则元数据，不读取配置或凭据。 */
public class ExportConfigurationFields {
    public static void main(String[] args) {
        System.setOut(
                new java.io.PrintStream(System.out, true, java.nio.charset.StandardCharsets.UTF_8));
        for (var section : ConfigurationCatalog.sections()) {
            for (var field : section.fields()) {
                System.out.println(
                        String.join(
                                "\t",
                                section.key(),
                                section.label(),
                                field.key(),
                                field.label(),
                                field.type(),
                                String.valueOf(field.required()),
                                String.valueOf(field.defaultValue()),
                                String.valueOf(field.minimum()),
                                String.valueOf(field.maximum()),
                                String.join("|", field.options())));
            }
        }
    }
}
