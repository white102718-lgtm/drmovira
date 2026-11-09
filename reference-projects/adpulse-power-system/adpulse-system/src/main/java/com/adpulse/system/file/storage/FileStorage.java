package com.adpulse.system.file.storage;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Path;
import org.springframework.core.io.Resource;

/** 物理文件存储抽象。 */
public interface FileStorage {
    Path createTemporaryFile() throws IOException;

    OutputStream openTemporaryOutput(Path temporaryFile) throws IOException;

    void promote(Path temporaryFile, String objectKey) throws IOException;

    Resource load(String bucketName, String objectKey);

    void deleteTemporary(Path temporaryFile);
}
