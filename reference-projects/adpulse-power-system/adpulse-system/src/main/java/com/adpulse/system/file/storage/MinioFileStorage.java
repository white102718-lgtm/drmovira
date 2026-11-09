package com.adpulse.system.file.storage;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.file.config.FileStorageProperties;
import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.GetObjectResponse;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.UploadObjectArgs;
import io.minio.errors.ErrorResponseException;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.util.StringUtils;

/** 基于私有MinIO桶的文件存储实现。 */
public class MinioFileStorage implements FileStorage {
    private final Path temporaryRoot;
    private final String bucket;
    private final MinioClient client;
    private volatile boolean bucketReady;

    public MinioFileStorage(FileStorageProperties properties) {
        requireConfiguration(properties);
        this.temporaryRoot =
                Path.of(properties.rootDirectory()).toAbsolutePath().normalize().resolve("tmp");
        this.bucket = properties.bucket();
        this.client =
                MinioClient.builder()
                        .endpoint(properties.endpoint())
                        .credentials(properties.accessKey(), properties.secretKey())
                        .build();
    }

    /** 创建上传校验所需的本地临时目录，MinIO桶在首次上传时检查并创建。 */
    @PostConstruct
    public void initialize() throws IOException {
        Files.createDirectories(temporaryRoot);
    }

    @Override
    public Path createTemporaryFile() throws IOException {
        return Files.createTempFile(temporaryRoot, "upload-", ".upload");
    }

    @Override
    public OutputStream openTemporaryOutput(Path temporaryFile) throws IOException {
        return Files.newOutputStream(requireTemporaryFile(temporaryFile));
    }

    @Override
    public void promote(Path temporaryFile, String objectKey) throws IOException {
        Path source = requireTemporaryFile(temporaryFile);
        try {
            ensureBucket();
            client.uploadObject(
                    UploadObjectArgs.builder()
                            .bucket(bucket)
                            .object(objectKey)
                            .filename(source.toString())
                            .build());
            Files.deleteIfExists(source);
        } catch (Exception exception) {
            throw new IOException("上传文件到MinIO失败", exception);
        }
    }

    @Override
    public Resource load(String bucketName, String objectKey) {
        String storedBucket = StringUtils.hasText(bucketName) ? bucketName : bucket;
        try {
            GetObjectResponse response =
                    client.getObject(
                            GetObjectArgs.builder().bucket(storedBucket).object(objectKey).build());
            return new InputStreamResource(response);
        } catch (ErrorResponseException exception) {
            if ("NoSuchKey".equals(exception.errorResponse().code())) {
                throw BusinessException.notFound("文件内容");
            }
            throw new IllegalStateException("从MinIO读取文件失败", exception);
        } catch (Exception exception) {
            throw new IllegalStateException("从MinIO读取文件失败", exception);
        }
    }

    @Override
    public void deleteTemporary(Path temporaryFile) {
        if (temporaryFile == null) return;
        try {
            Files.deleteIfExists(requireTemporaryFile(temporaryFile));
        } catch (IOException ignored) {
            // 临时文件由定时清理作为最终兜底，不覆盖原始业务异常。
        }
    }

    private void ensureBucket() throws Exception {
        if (bucketReady) return;
        synchronized (this) {
            if (bucketReady) return;
            boolean exists = client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!exists) client.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
            bucketReady = true;
        }
    }

    private Path requireTemporaryFile(Path path) {
        Path resolved = path.toAbsolutePath().normalize();
        if (!resolved.startsWith(temporaryRoot)) throw BusinessException.validation("非法临时文件路径");
        return resolved;
    }

    private static void requireConfiguration(FileStorageProperties properties) {
        if (!StringUtils.hasText(properties.rootDirectory())
                || properties.maxSize() == null
                || !StringUtils.hasText(properties.endpoint())
                || !StringUtils.hasText(properties.accessKey())
                || !StringUtils.hasText(properties.secretKey())
                || !StringUtils.hasText(properties.bucket())) {
            throw new IllegalStateException("MinIO文件存储配置不完整");
        }
    }
}
