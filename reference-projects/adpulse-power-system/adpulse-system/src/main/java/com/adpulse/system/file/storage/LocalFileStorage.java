package com.adpulse.system.file.storage;

import com.adpulse.system.common.exception.BusinessException;
import com.adpulse.system.file.config.FileStorageProperties;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

/** 基于独立数据目录的本地文件存储实现。 */
public class LocalFileStorage implements FileStorage {
    private final Path root;
    private final Path temporaryRoot;

    public LocalFileStorage(FileStorageProperties properties) {
        this.root = Path.of(properties.rootDirectory()).toAbsolutePath().normalize();
        this.temporaryRoot = root.resolve("tmp").normalize();
    }

    /** 确保存储根目录和临时目录在启动时可用。 */
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
        return Files.newOutputStream(requireInsideRoot(temporaryFile));
    }

    @Override
    public void promote(Path temporaryFile, String objectKey) throws IOException {
        Path source = requireInsideRoot(temporaryFile);
        Path target = resolveObject(objectKey);
        Files.createDirectories(target.getParent());
        if (Files.exists(target)) {
            Files.deleteIfExists(source);
            return;
        }
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (java.nio.file.AtomicMoveNotSupportedException exception) {
            Files.move(source, target);
        } catch (java.nio.file.FileAlreadyExistsException exception) {
            Files.deleteIfExists(source);
        }
    }

    @Override
    public Resource load(String bucketName, String objectKey) {
        Path path = resolveObject(objectKey);
        if (!Files.isRegularFile(path)) throw BusinessException.notFound("文件内容");
        return new FileSystemResource(path);
    }

    @Override
    public void deleteTemporary(Path temporaryFile) {
        if (temporaryFile == null) return;
        try {
            Files.deleteIfExists(requireInsideRoot(temporaryFile));
        } catch (IOException ignored) {
            // 临时文件由定时清理作为最终兜底，不覆盖原始业务异常。
        }
    }

    private Path resolveObject(String objectKey) {
        return requireInsideRoot(root.resolve(objectKey).normalize());
    }

    private Path requireInsideRoot(Path path) {
        Path resolved = path.toAbsolutePath().normalize();
        if (!resolved.startsWith(root)) throw BusinessException.validation("非法文件路径");
        return resolved;
    }
}
