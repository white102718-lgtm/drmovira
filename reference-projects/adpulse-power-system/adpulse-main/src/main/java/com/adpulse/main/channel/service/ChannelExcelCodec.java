package com.adpulse.main.channel.service;

import com.adpulse.main.channel.dto.ChannelViews;
import com.adpulse.main.channel.service.ChannelService.ChannelException;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.apache.poi.ss.usermodel.Cell;
import org.apache.poi.ss.usermodel.CellType;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.ss.usermodel.Workbook;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.springframework.stereotype.Component;

/** 渠道账户 Excel 导入导出编解码器。 */
@Component
public class ChannelExcelCodec {
    private static final String[] IMPORT_HEADERS = {
        "渠道ID", "账户ID", "账户类型", "账户名称", "所属主体", "时区", "账户状态", "使用状态", "余额", "花费", "备注"
    };

    /** 解析账户导入工作簿。 */
    public List<ImportRow> read(byte[] content) {
        try (Workbook workbook = new XSSFWorkbook(new ByteArrayInputStream(content))) {
            Sheet sheet = workbook.getSheetAt(0);
            List<ImportRow> result = new ArrayList<>();
            for (int index = 1; index <= sheet.getLastRowNum(); index++) {
                Row row = sheet.getRow(index);
                if (row == null || text(row.getCell(0)).isBlank()) continue;
                result.add(
                        new ImportRow(
                                index + 1,
                                text(row.getCell(0)),
                                text(row.getCell(1)).replaceFirst("^act_", ""),
                                text(row.getCell(2)),
                                text(row.getCell(3)),
                                text(row.getCell(4)),
                                integer(row.getCell(5), 0),
                                integer(row.getCell(6), 1),
                                integer(row.getCell(7), 0),
                                decimal(row.getCell(8)),
                                decimal(row.getCell(9)),
                                text(row.getCell(10))));
            }
            if (result.isEmpty()) throw new ChannelException("导入文件没有有效数据");
            return result;
        } catch (ChannelException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new ChannelException("无法读取 Excel 文件，请使用下载的模板");
        }
    }

    /** 生成带示例行的账户导入模板。 */
    public byte[] template() {
        try (Workbook workbook = new XSSFWorkbook()) {
            Sheet sheet = workbook.createSheet("渠道账户导入");
            Row header = sheet.createRow(0);
            for (int i = 0; i < IMPORT_HEADERS.length; i++) {
                header.createCell(i).setCellValue(IMPORT_HEADERS[i]);
                sheet.setColumnWidth(i, i == 10 ? 7000 : 4500);
            }
            Row sample = sheet.createRow(1);
            Object[] values = {
                "1", "123456789012345", "企业户", "示例账户", "示例主体", 8, 1, 0, 1000, 25.5, "示例行，导入前请删除"
            };
            for (int i = 0; i < values.length; i++) {
                Cell cell = sample.createCell(i);
                if (values[i] instanceof Number number) cell.setCellValue(number.doubleValue());
                else cell.setCellValue(String.valueOf(values[i]));
            }
            return bytes(workbook);
        } catch (Exception exception) {
            throw new ChannelException("生成导入模板失败");
        }
    }

    /** 导出账户查询结果。 */
    public byte[] write(List<ChannelViews.Account> accounts) {
        try (Workbook workbook = new XSSFWorkbook()) {
            Sheet sheet = workbook.createSheet("渠道账户");
            String[] headers = {
                "账户ID", "账户名称", "账户类型", "FB账户ID", "时区", "BM", "管理BM", "开户费", "买户费(￥)",
                "买户费($)", "花费", "余额", "卡扣金额", "总花费", "剩余应付", "账户状态", "使用状态", "所属主体",
                "使用人", "使用团队", "开户日期", "下户日期", "分配时间", "备注"
            };
            Row header = sheet.createRow(0);
            for (int i = 0; i < headers.length; i++) header.createCell(i).setCellValue(headers[i]);
            int rowIndex = 1;
            for (ChannelViews.Account account : accounts) {
                Row row = sheet.createRow(rowIndex++);
                Object[] values = {
                    account.accountId(), account.accountName(), account.accountType(),
                            account.fbAccountId(),
                    account.timezone(), account.bmId(), account.bmFromFeishu(),
                            account.openingBalance(),
                    account.byBalance(), account.byBalanceU(), account.consumption(),
                            account.balance(),
                    account.actualDeduction(), account.amountSpent(), account.remainingSpendCap(),
                            account.status(),
                    account.usageStatus(), account.subjectName(), account.operatorName(),
                            account.belongTeam(),
                    account.openDate(), account.createTime(), account.assignTime(), account.remark()
                };
                for (int i = 0; i < values.length; i++) set(row.createCell(i), values[i]);
            }
            for (int i = 0; i < headers.length; i++) sheet.setColumnWidth(i, 4600);
            return bytes(workbook);
        } catch (Exception exception) {
            throw new ChannelException("导出渠道账户失败");
        }
    }

    private byte[] bytes(Workbook workbook) throws java.io.IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        workbook.write(output);
        return output.toByteArray();
    }

    private void set(Cell cell, Object value) {
        if (value == null) cell.setCellValue("");
        else if (value instanceof Number number) cell.setCellValue(number.doubleValue());
        else cell.setCellValue(String.valueOf(value));
    }

    private String text(Cell cell) {
        if (cell == null) return "";
        if (cell.getCellType() == CellType.NUMERIC) {
            double number = cell.getNumericCellValue();
            if (number == Math.rint(number))
                return BigDecimal.valueOf(number).toBigInteger().toString();
            return BigDecimal.valueOf(number).stripTrailingZeros().toPlainString();
        }
        return cell.toString().trim();
    }

    private BigDecimal decimal(Cell cell) {
        String value = text(cell);
        return value.isBlank() ? BigDecimal.ZERO : new BigDecimal(value);
    }

    private int integer(Cell cell, int fallback) {
        String value = text(cell);
        return value.isBlank() ? fallback : new BigDecimal(value).intValueExact();
    }

    /** Excel 导入行。 */
    public record ImportRow(
            int rowNumber,
            String channelId,
            String accountId,
            String accountType,
            String accountName,
            String subjectName,
            int timezone,
            int status,
            int usageStatus,
            BigDecimal balance,
            BigDecimal consumption,
            String remark) {}
}
