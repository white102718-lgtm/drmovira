package com.adpulse.system.file.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.CurrentUser;
import com.adpulse.system.file.config.FileStorageProperties;
import com.adpulse.system.file.dto.FileRequests;
import com.adpulse.system.file.dto.FileResponses;
import com.adpulse.system.file.mapper.FileMapper;
import com.adpulse.system.file.model.FileObject;
import com.adpulse.system.file.model.StoredFile;
import com.adpulse.system.file.storage.LocalFileStorage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.util.unit.DataSize;

/** 文件去重、校验和所有者规则测试。 */
@ExtendWith(MockitoExtension.class)
class FileServiceTest {
    @TempDir Path temporaryDirectory;
    @Mock private FileMapper mapper;

    private FileService service;

    @BeforeEach
    void setUp() throws Exception {
        CurrentUser user = new CurrentUser(7L, "session", "测试用户", List.of());
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", List.of()));
        FileStorageProperties properties =
                new FileStorageProperties(
                        temporaryDirectory.toString(),
                        DataSize.ofMegabytes(100),
                        "http://127.0.0.1:9000",
                        "test-access-key",
                        "test-secret-key",
                        "adpulse-files");
        LocalFileStorage storage = new LocalFileStorage(properties);
        storage.initialize();
        service = new FileService(mapper, storage, properties);
    }

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.ValueSource(
            strings = {"AM", "OPERATOR_LEADER", "ADMIN", "USER"})
    void reportScreenshotDownloadUsesSameRoleScope(String role) {
        var authorities =
                List.of(
                        new org.springframework.security.core.authority.SimpleGrantedAuthority(
                                "ROLE_" + role));
        var user = new CurrentUser(7L, "session", "用户", authorities);
        SecurityContextHolder.getContext()
                .setAuthentication(new UsernamePasswordAuthenticationToken(user, "", authorities));
        assertThatThrownBy(() -> service.download(42L)).isInstanceOf(BusinessException.class);
        verify(mapper).findReadableFile(42L, 7L, false, !role.equals("USER"));
    }

    @AfterEach
    void clearCurrentUser() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void shouldCreateOwnedReferenceWhenPrecheckHits() {
        FileObject object = object(11L, "a".repeat(64), 12L);
        when(mapper.findAvailableObject(object.getContentHash(), 12L)).thenReturn(object);
        when(mapper.incrementReference(11L, 7L)).thenReturn(1);
        when(mapper.insertFile(any(StoredFile.class)))
                .thenAnswer(
                        invocation -> {
                            invocation.<StoredFile>getArgument(0).setId(21L);
                            return 1;
                        });
        StoredFile stored = new StoredFile();
        stored.setId(21L);
        stored.setUploaderId(7L);
        when(mapper.findOwnedFile(21L, 7L)).thenReturn(stored);

        FileResponses.PrecheckResult result =
                service.precheck(
                        new FileRequests.Precheck("report.pdf", 12L, object.getContentHash()));

        assertThat(result.instantUpload()).isTrue();
        assertThat(result.file().getId()).isEqualTo(21L);
        verify(mapper).incrementReference(11L, 7L);
    }

    @Test
    void shouldRejectDeletingScreenshotBoundToDeliveryReport() {
        StoredFile file = new StoredFile();
        file.setId(21L);
        when(mapper.findOwnedFile(21L, 7L)).thenReturn(file);
        when(mapper.countActiveDeliveryReportBindings(21L)).thenReturn(1);

        assertThatThrownBy(() -> service.delete(21L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("投放日报引用");
    }

    @Test
    void shouldRejectUploadWhenServerHashDiffers() throws Exception {
        byte[] content = "actual content".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile("file", "note.txt", "text/plain", content);

        assertThatThrownBy(() -> service.upload(file, "0".repeat(64)))
                .isInstanceOf(BusinessException.class)
                .hasMessage("文件SHA-256校验失败");
    }

    @Test
    void shouldStoreNewObjectByHashPath() throws Exception {
        byte[] content = "file content".getBytes(StandardCharsets.UTF_8);
        String hash =
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content));
        MockMultipartFile multipart =
                new MockMultipartFile("file", "note.txt", "text/plain", content);
        when(mapper.findAvailableObject(hash, content.length)).thenReturn(null);
        when(mapper.insertObject(any(FileObject.class)))
                .thenAnswer(
                        invocation -> {
                            invocation.<FileObject>getArgument(0).setId(31L);
                            return 1;
                        });
        when(mapper.incrementReference(31L, 7L)).thenReturn(1);
        when(mapper.insertFile(any(StoredFile.class)))
                .thenAnswer(
                        invocation -> {
                            invocation.<StoredFile>getArgument(0).setId(41L);
                            return 1;
                        });
        StoredFile result = new StoredFile();
        result.setId(41L);
        when(mapper.findOwnedFile(41L, 7L)).thenReturn(result);

        StoredFile uploaded = service.upload(multipart, hash);

        assertThat(uploaded.getId()).isEqualTo(41L);
        verify(mapper)
                .insertObject(
                        org.mockito.ArgumentMatchers.argThat(
                                object ->
                                        "MINIO".equals(object.getStorageProvider())
                                                && "adpulse-files".equals(object.getBucketName())));
        assertThat(
                        temporaryDirectory
                                .resolve(
                                        "sha256/"
                                                + hash.substring(0, 2)
                                                + "/"
                                                + hash.substring(2, 4)
                                                + "/"
                                                + hash)
                                .toFile())
                .exists();
    }

    @Test
    void shouldSoftDeleteOnlyOwnedFileAndDecrementReference() {
        StoredFile file = new StoredFile();
        file.setId(51L);
        file.setFileObjectId(61L);
        when(mapper.findOwnedFile(51L, 7L)).thenReturn(file);
        when(mapper.softDeleteFile(eq(51L), eq(7L), anyLong(), eq(7L))).thenReturn(1);
        when(mapper.decrementReference(61L, 7L)).thenReturn(1);

        service.delete(51L);

        verify(mapper).decrementReference(61L, 7L);
    }

    @Test
    void shouldRejectDeletingFileBoundToTask() {
        StoredFile file = new StoredFile();
        file.setId(51L);
        file.setFileObjectId(61L);
        when(mapper.findOwnedFile(51L, 7L)).thenReturn(file);
        when(mapper.countActiveTaskBindings(51L)).thenReturn(1);

        assertThatThrownBy(() -> service.delete(51L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("任务或交付引用");
    }

    @Test
    void shouldReturnActiveFileWithoutOwnershipCheck() {
        StoredFile file = new StoredFile();
        file.setId(96L);
        file.setUploaderId(1L);
        when(mapper.findActiveFile(96L)).thenReturn(file);

        assertThat(service.openDetail(96L)).isSameAs(file);
        verify(mapper).findActiveFile(96L);
    }

    @Test
    void shouldDownloadActiveFileWithoutOwnershipCheck() throws Exception {
        Files.writeString(temporaryDirectory.resolve("receipt.png"), "receipt");
        StoredFile file = new StoredFile();
        file.setId(96L);
        file.setUploaderId(1L);
        file.setObjectKey("receipt.png");
        when(mapper.findActiveFile(96L)).thenReturn(file);

        FileResponses.DownloadFile download = service.openDownload(96L);

        assertThat(download.file()).isSameAs(file);
        assertThat(download.resource().exists()).isTrue();
    }

    @Test
    void shouldHideMissingOrInactiveFileFromOpenEndpoint() {
        when(mapper.findActiveFile(96L)).thenReturn(null);

        assertThatThrownBy(() -> service.openDetail(96L))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("文件");
    }

    private FileObject object(Long id, String hash, Long size) {
        FileObject object = new FileObject();
        object.setId(id);
        object.setContentHash(hash);
        object.setFileSize(size);
        return object;
    }
}
