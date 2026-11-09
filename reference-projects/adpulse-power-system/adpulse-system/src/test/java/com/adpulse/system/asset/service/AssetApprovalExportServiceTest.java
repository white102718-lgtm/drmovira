package com.adpulse.system.asset.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.adpulse.system.asset.mapper.DynamicAssetFlowMapper;
import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.file.storage.FileStorage;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.imageio.ImageIO;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class AssetApprovalExportServiceTest {
    private DynamicAssetFlowMapper mapper;
    private FileStorage storage;
    private AssetApprovalExportService service;

    @BeforeEach
    void setUp() {
        mapper = mock(DynamicAssetFlowMapper.class);
        storage = mock(FileStorage.class);
        service = new AssetApprovalExportService(mapper, storage, new ObjectMapper());
        SecurityContextHolder.getContext()
                .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                                new CurrentUser(42L, "session", "测试用户", List.of()), null));
    }

    @AfterEach
    void tearDown() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldExportDynamicResultColumnsAndEmbedReceiptImage() throws Exception {
        byte[] receipt = png();
        when(mapper.findVisibleApprovalExportRows(anyMap())).thenReturn(List.of(application()));
        when(mapper.findApprovalLogsByApplicationIds(anyList()))
                .thenReturn(List.of(completedLog()));
        when(mapper.findAllocatedAssetsByApplicationIds(anyList())).thenReturn(List.of());
        when(mapper.findApprovalExportFiles(anyList()))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id",
                                        7L,
                                        "originalName",
                                        "水单.png",
                                        "fileSize",
                                        (long) receipt.length,
                                        "mimeType",
                                        "image/png",
                                        "bucketName",
                                        "files",
                                        "objectKey",
                                        "receipt.png")));
        when(storage.load("files", "receipt.png")).thenReturn(new ByteArrayResource(receipt));

        byte[] content = service.export(List.of(31L, 31L));

        try (XSSFWorkbook workbook = new XSSFWorkbook(new ByteArrayInputStream(content))) {
            var sheet = workbook.getSheet("审批记录");
            assertThat(sheet.getRow(0).getCell(19).getStringCellValue()).isEqualTo("实际打款金额");
            assertThat(sheet.getRow(0).getCell(20).getStringCellValue()).isEqualTo("水单图片");
            assertThat(sheet.getRow(1).getCell(19).getStringCellValue()).isEqualTo("123.45");
            assertThat(sheet.getDrawingPatriarch().getShapes()).hasSize(1);
            assertThat(workbook.getAllPictures())
                    .singleElement()
                    .satisfies(picture -> assertThat(picture.getData()).isEqualTo(receipt));
        }
    }

    @Test
    void shouldRejectWhenAnySelectedApplicationIsNotVisible() {
        when(mapper.findVisibleApprovalExportRows(anyMap())).thenReturn(List.of(application()));

        assertThatThrownBy(() -> service.export(List.of(31L, 32L)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("无权导出");
    }

    @Test
    void shouldRejectImagePayloadAboveFiftyMegabytesBeforeReadingStorage() {
        when(mapper.findVisibleApprovalExportRows(anyMap())).thenReturn(List.of(application()));
        when(mapper.findApprovalLogsByApplicationIds(anyList()))
                .thenReturn(List.of(completedLog()));
        when(mapper.findAllocatedAssetsByApplicationIds(anyList())).thenReturn(List.of());
        when(mapper.findApprovalExportFiles(anyList()))
                .thenReturn(
                        List.of(
                                Map.of(
                                        "id",
                                        7L,
                                        "originalName",
                                        "水单.png",
                                        "fileSize",
                                        AssetApprovalExportService.MAX_IMAGE_BYTES + 1,
                                        "mimeType",
                                        "image/png",
                                        "bucketName",
                                        "files",
                                        "objectKey",
                                        "receipt.png")));

        assertThatThrownBy(() -> service.export(List.of(31L)))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("超过 50MB");
    }

    private Map<String, Object> application() {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", 31L);
        row.put("applicationNo", "APP-31");
        row.put("applicationTypeName", "打款申请");
        row.put("assetType", "PAYMENT");
        row.put("title", "渠道打款");
        row.put("quantity", 1);
        row.put("reason", "补充余额");
        row.put("status", "APPROVED");
        row.put("requesterName", "申请人");
        row.put("departmentName", "投放部");
        row.put("projectName", "渠道 A");
        row.put("approverName", "审批人");
        row.put("createdAt", LocalDateTime.of(2026, 9, 18, 9, 0));
        row.put("updatedAt", LocalDateTime.of(2026, 9, 18, 10, 0));
        row.put(
                "nodes",
                "[{\"handlerAction\":{\"formSchema\":["
                        + "{\"key\":\"actualAmount\",\"label\":\"实际打款金额\",\"type\":\"number\"},"
                        + "{\"key\":\"receiptFileIds\",\"label\":\"水单图片\",\"type\":\"image-upload\"}]}}]");
        return row;
    }

    private Map<String, Object> completedLog() {
        return Map.of(
                "applicationId",
                31L,
                "id",
                101L,
                "action",
                "COMPLETED",
                "actorName",
                "办理人",
                "remark",
                "已打款",
                "actionData",
                "{\"actualAmount\":123.45,\"receiptFileIds\":[7]}",
                "createdAt",
                LocalDateTime.of(2026, 9, 18, 10, 0));
    }

    private byte[] png() throws Exception {
        BufferedImage image = new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        ImageIO.write(image, "png", output);
        return output.toByteArray();
    }
}
