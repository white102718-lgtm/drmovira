package com.adpulse.system.file.service;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.common.security.SecurityContextHelper;
import com.adpulse.system.feedback.service.FeedbackService;
import com.adpulse.system.file.config.FileStorageProperties;
import com.adpulse.system.file.dto.FileRequests;
import com.adpulse.system.file.dto.FileResponses;
import com.adpulse.system.file.mapper.FileMapper;
import com.adpulse.system.file.model.FileObject;
import com.adpulse.system.file.model.StoredFile;
import com.adpulse.system.file.storage.FileStorage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

/** 文件去重、元数据和所有者访问控制业务。 */
@Service
public class FileService {
    private static final String HASH_PATTERN = "[0-9a-f]{64}";
    private static final Object[] HASH_LOCKS = createHashLocks();

    private final FileMapper mapper;
    private final FileStorage storage;
    private final FileStorageProperties storageProperties;
    private final long maxSize;

    public FileService(
            FileMapper mapper, FileStorage storage, FileStorageProperties storageProperties) {
        this.mapper = mapper;
        this.storage = storage;
        this.storageProperties = storageProperties;
        this.maxSize = storageProperties.maxSize().toBytes();
    }

    /** 根据客户端文件摘要尝试秒传。 */
    @Transactional
    public FileResponses.PrecheckResult precheck(FileRequests.Precheck request) {
        validateSize(request.fileSize());
        String hash = normalizeHash(request.contentHash());
        String fileName = normalizeFileName(request.fileName());
        FileObject object = mapper.findAvailableObject(hash, request.fileSize());
        if (object == null) return new FileResponses.PrecheckResult(false, null);
        StoredFile file = createReference(object, fileName);
        return new FileResponses.PrecheckResult(true, file);
    }

    /** 流式写入文件并以服务端SHA-256核验客户端摘要。 */
    @Transactional
    public StoredFile upload(MultipartFile multipartFile, String clientHash) {
        if (multipartFile == null || multipartFile.isEmpty())
            throw BusinessException.validation("上传文件不能为空");
        validateSize(multipartFile.getSize());
        String expectedHash = normalizeHash(clientHash);
        String fileName = normalizeFileName(multipartFile.getOriginalFilename());
        Path temporaryFile = null;
        try {
            temporaryFile = storage.createTemporaryFile();
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long actualSize;
            try (InputStream input = new DigestInputStream(multipartFile.getInputStream(), digest);
                    OutputStream output = storage.openTemporaryOutput(temporaryFile)) {
                actualSize = input.transferTo(output);
            }
            validateSize(actualSize);
            if (actualSize != multipartFile.getSize())
                throw BusinessException.validation("文件大小与上传声明不一致");
            String actualHash = HexFormat.of().formatHex(digest.digest());
            if (!actualHash.equals(expectedHash))
                throw BusinessException.validation("文件SHA-256校验失败");

            synchronized (HASH_LOCKS[actualHash.hashCode() & (HASH_LOCKS.length - 1)]) {
                FileObject object = mapper.findAvailableObject(actualHash, actualSize);
                if (object == null) {
                    String objectKey = objectKey(actualHash);
                    storage.promote(temporaryFile, objectKey);
                    temporaryFile = null;
                    object =
                            newFileObject(
                                    actualHash, actualSize, detectMime(multipartFile), objectKey);
                    mapper.insertObject(object);
                } else {
                    storage.deleteTemporary(temporaryFile);
                    temporaryFile = null;
                }
                return createReference(object, fileName);
            }
        } catch (BusinessException exception) {
            throw exception;
        } catch (IOException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("文件存储失败", exception);
        } finally {
            storage.deleteTemporary(temporaryFile);
        }
    }

    /** 查询当前用户拥有的文件记录。 */
    public StoredFile detail(Long id) {
        return requireOwned(id);
    }

    /** 获取当前用户文件的下载资源。 */
    public FileResponses.DownloadFile download(Long id) {
        StoredFile file = requireReadable(id);
        return new FileResponses.DownloadFile(
                file, storage.load(file.getBucketName(), file.getObjectKey()));
    }

    /** 获取登录用户可直接读取的有效文件元数据，不附加上传人或业务关联校验。 */
    public StoredFile openDetail(Long id) {
        return requireActive(id);
    }

    /** 获取登录用户可直接读取的有效文件内容，不附加上传人或业务关联校验。 */
    public FileResponses.DownloadFile openDownload(Long id) {
        StoredFile file = requireActive(id);
        return new FileResponses.DownloadFile(
                file, storage.load(file.getBucketName(), file.getObjectKey()));
    }

    /** 软删除当前用户的文件记录并递减物理对象引用。 */
    @Transactional
    public void delete(Long id) {
        StoredFile file = requireOwned(id);
        if (mapper.countActiveDeliveryReportBindings(id) > 0)
            throw BusinessException.conflict("截图已被投放日报引用，请先在日报中移除并保存");
        if (mapper.countActiveTaskBindings(id) > 0 || mapper.countActiveFeedbackBindings(id) > 0)
            throw BusinessException.conflict("文件已被任务或交付引用，或已作为反馈附件，不能删除");
        Long userId = SecurityContextHelper.currentUserId();
        if (mapper.softDeleteFile(id, userId, System.currentTimeMillis(), userId) != 1)
            throw BusinessException.notFound("文件");
        if (mapper.decrementReference(file.getFileObjectId(), userId) != 1)
            throw BusinessException.conflict("文件引用状态异常");
    }

    private StoredFile createReference(FileObject object, String fileName) {
        Long userId = SecurityContextHelper.currentUserId();
        if (mapper.incrementReference(object.getId(), userId) != 1)
            throw BusinessException.conflict("文件存储状态已变化，请重试");
        StoredFile file = new StoredFile();
        file.setFileObjectId(object.getId());
        file.setOriginalName(fileName);
        file.setExtension(extension(fileName));
        file.setUploaderId(userId);
        file.setCreatedBy(userId);
        file.setUpdatedBy(userId);
        mapper.insertFile(file);
        return mapper.findOwnedFile(file.getId(), userId);
    }

    private FileObject newFileObject(String hash, long size, String mimeType, String objectKey) {
        Long userId = SecurityContextHelper.currentUserId();
        FileObject object = new FileObject();
        object.setContentHash(hash);
        object.setHashAlgorithm("SHA-256");
        object.setFileSize(size);
        object.setMimeType(mimeType);
        object.setStorageProvider("MINIO");
        object.setBucketName(storageProperties.bucket());
        object.setObjectKey(objectKey);
        object.setStorageStatus("AVAILABLE");
        object.setReferenceCount(0L);
        object.setCreatedBy(userId);
        object.setUpdatedBy(userId);
        return object;
    }

    private StoredFile requireOwned(Long id) {
        StoredFile file = mapper.findOwnedFile(id, SecurityContextHelper.currentUserId());
        if (file == null) throw BusinessException.notFound("文件");
        return file;
    }

    private StoredFile requireActive(Long id) {
        StoredFile file = mapper.findActiveFile(id);
        if (file == null) throw BusinessException.notFound("文件");
        return file;
    }

    private StoredFile requireReadable(Long id) {
        var user = SecurityContextHelper.currentUser();
        boolean canManageFeedback =
                user.authorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .anyMatch(FeedbackService.MANAGE_AUTHORITY::equals);
        StoredFile file =
                mapper.findReadableFile(
                        id,
                        user.userId(),
                        canManageFeedback,
                        com.adpulse.system.common.security.DeliveryReportAccess.canReadAll(user));
        if (file == null) throw BusinessException.notFound("文件");
        return file;
    }

    private void validateSize(long size) {
        if (size <= 0) throw BusinessException.validation("文件大小必须大于0");
        if (size > maxSize)
            throw BusinessException.validation("单个文件不能超过" + (maxSize / 1024 / 1024) + " MB");
    }

    private String normalizeHash(String hash) {
        String value = hash == null ? "" : hash.trim().toLowerCase(Locale.ROOT);
        if (!value.matches(HASH_PATTERN)) throw BusinessException.validation("文件SHA-256格式不正确");
        return value;
    }

    private String normalizeFileName(String originalName) {
        String value = originalName == null ? "" : originalName.replace('\\', '/');
        value = value.substring(value.lastIndexOf('/') + 1).trim();
        value = value.replaceAll("[\\p{Cntrl}]", "");
        if (value.isBlank()) throw BusinessException.validation("文件名不能为空");
        if (value.length() > 255) throw BusinessException.validation("文件名不能超过255个字符");
        return value;
    }

    private String extension(String fileName) {
        int dot = fileName.lastIndexOf('.');
        if (dot <= 0 || dot == fileName.length() - 1) return null;
        String value = fileName.substring(dot + 1).toLowerCase(Locale.ROOT);
        return value.length() <= 32 ? value : null;
    }

    private String detectMime(MultipartFile file) {
        String contentType = file.getContentType();
        if (contentType == null || contentType.isBlank() || contentType.length() > 128)
            return "application/octet-stream";
        return contentType.toLowerCase(Locale.ROOT);
    }

    private String objectKey(String hash) {
        return "sha256/" + hash.substring(0, 2) + "/" + hash.substring(2, 4) + "/" + hash;
    }

    private static Object[] createHashLocks() {
        Object[] locks = new Object[256];
        java.util.Arrays.setAll(locks, ignored -> new Object());
        return locks;
    }
}
