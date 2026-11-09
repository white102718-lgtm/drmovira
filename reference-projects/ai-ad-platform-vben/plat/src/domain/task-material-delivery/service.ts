import type { TaskMaterialDeliveryAdapter } from './adapter';
import type {
  MaterialDeliveryFile,
  MaterialDeliverySubmission,
  MaterialDeliverySubmitInput,
  MaterialOrderDeliveryContext,
} from './types';

function nonEmpty(value: string | undefined) {
  return Boolean(value?.trim());
}

function asNonNegativeNumber(value: unknown) {
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

function cloneFile(file: MaterialDeliveryFile): MaterialDeliveryFile {
  return { ...file };
}

/**
 * Validates server-uploaded material facts before calling the legacy deliver
 * endpoint. It intentionally has no "complete" operation: delivery only puts
 * the MaterialOrder into pending acceptance.
 */
export class TaskMaterialDeliveryService {
  constructor(private readonly adapter: TaskMaterialDeliveryAdapter) {}

  deliver(
    input: MaterialDeliverySubmitInput,
  ): Promise<MaterialDeliverySubmission> {
    const normalized: MaterialDeliverySubmitInput = {
      ...input,
      files: input.files.map((file) => ({
        ...cloneFile(file),
        duration: asNonNegativeNumber(file.duration),
        height: asNonNegativeNumber(file.height),
        size: asNonNegativeNumber(file.size),
        width: asNonNegativeNumber(file.width),
      })),
    };
    this.validateSubmitInput(normalized);
    return this.adapter.deliver(normalized);
  }

  getContext(orderId: string): Promise<MaterialOrderDeliveryContext> {
    if (!orderId.trim()) {
      return Promise.reject(new Error('素材任务缺少稳定的素材订单 ID'));
    }
    return this.adapter.getContext(orderId.trim());
  }

  private validateSubmitInput(input: MaterialDeliverySubmitInput) {
    if (!input.orderId.trim()) {
      throw new Error('素材任务缺少稳定的素材订单 ID');
    }
    if (input.files.length === 0) {
      throw new Error('请至少上传 1 个素材文件');
    }

    const objectKeys = new Set<string>();
    for (const file of input.files) {
      if (
        !nonEmpty(file.id) ||
        !nonEmpty(file.objectKey) ||
        !nonEmpty(file.name) ||
        !nonEmpty(file.basename) ||
        !nonEmpty(file.contentType) ||
        !nonEmpty(file.filetype) ||
        !nonEmpty(file.fileMd5) ||
        !nonEmpty(file.sha3_256)
      ) {
        throw new Error('素材文件尚未完成服务端上传，请重新上传后再提交');
      }
      if (file.objectKey.startsWith('task-completion/')) {
        throw new Error(
          '素材文件必须来自素材订单上传，不可使用任务中心本地附件',
        );
      }
      if (objectKeys.has(file.objectKey)) {
        throw new Error(`素材文件重复：${file.name}`);
      }
      objectKeys.add(file.objectKey);
    }
  }
}
