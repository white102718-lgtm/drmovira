"""真实本机子进程输出/超时边界，以及真实JPEG发布校验；不启动共享服务。"""

import subprocess
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from orbit_api import material_processing as processing
from orbit_api.errors import OrbitError
from orbit_api.material_contract import CompletedPart
from orbit_api.material_objects import LocalMaterialObjects


def test_real_processor_stdout_exact_limit_and_stderr_are_bounded():
    result = processing._run_processor(
        [sys.executable, "-c", "import os;os.write(1,b'x'*65536);os.write(2,b'y'*65536)"], timeout=5
    )
    assert result == b"x" * 65536


@pytest.mark.parametrize("descriptor", [1, 2])
def test_real_processor_overflow_kills_and_reaps_process(monkeypatch, descriptor):
    original = subprocess.Popen
    started = []

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(processing.subprocess, "Popen", launch)
    with pytest.raises(subprocess.SubprocessError, match="^PROCESSOR_OUTPUT_LIMIT$"):
        processing._run_processor(
            [sys.executable, "-c", f"import os\nwhile True:os.write({descriptor},b'x'*4096)"],
            timeout=5,
        )
    assert len(started) == 1 and started[0].poll() is not None
    assert started[0].stdout.closed and started[0].stderr.closed


def test_real_processor_timeout_kills_and_reaps_process(monkeypatch):
    original = subprocess.Popen
    started = []

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(processing.subprocess, "Popen", launch)
    with pytest.raises(subprocess.SubprocessError, match="^PROCESSOR_TIMEOUT$"):
        processing._run_processor([sys.executable, "-c", "import time;time.sleep(10)"], timeout=0.2)
    assert started[0].poll() is not None
    assert started[0].stdout.closed and started[0].stderr.closed


def test_real_processor_exit_failure_never_returns_success():
    with pytest.raises(subprocess.SubprocessError, match="^PROCESSOR_EXIT_FAILED$"):
        processing._run_processor([sys.executable, "-c", "raise SystemExit(2)"], timeout=5)


def image_bytes(format="JPEG", size=(20, 10)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format)
    return output.getvalue()


def test_real_jpeg_preview_verifies(tmp_path):
    target = tmp_path / "preview.jpg"
    target.write_bytes(image_bytes())
    processing._verify_preview(target)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not jpeg",
        image_bytes("PNG"),
        image_bytes(size=(1025, 1)),
        b"x" * (5 * 1024 * 1024 + 1),
    ],
)
def test_empty_fake_non_jpeg_oversize_preview_is_rejected(tmp_path, content):
    target = tmp_path / "preview.jpg"
    target.write_bytes(content)
    with pytest.raises(OrbitError) as error:
        processing._verify_preview(target)
    assert error.value.code == "PREVIEW_INVALID"


@pytest.mark.parametrize("content", [b"", image_bytes("PNG")])
def test_processor_success_cannot_publish_invalid_preview(tmp_path, monkeypatch, content):
    objects, tenant, upload = LocalMaterialObjects(tmp_path), str(uuid4()), str(uuid4())
    original = image_bytes("PNG")
    digest = objects.put_part(tenant, upload, 1, original, len(original))
    objects.assemble(
        tenant,
        upload,
        [CompletedPart(part_number=1, etag=digest)],
        len(original),
        digest,
        "image/png",
    )

    def invalid_processor(source: Path, target: Path, mime):
        target.write_bytes(content)
        return processing.ProcessedMaterial(20, 10, None)

    monkeypatch.setattr(processing, "_image", invalid_processor)
    with pytest.raises(OrbitError) as error:
        processing.process_material(objects, tenant, upload, "image/png")
    assert error.value.code == "PREVIEW_INVALID"
    directory = objects.directory(tenant, upload)
    assert not (directory / "preview.jpg").exists()
    assert not list(directory.glob("preview-*.jpg"))
