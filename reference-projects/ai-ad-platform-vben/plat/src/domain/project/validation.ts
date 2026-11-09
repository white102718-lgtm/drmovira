/** 与 Java String/@Size 一致，按 UTF-16 代码单元计数，保存时保留原文。 */
export const PRODUCT_INFO_MAX_LENGTH = 2000;

export function validateProductInfo(value: string) {
  if (!value?.trim()) throw new Error('请输入产品信息');
  if (value.length > PRODUCT_INFO_MAX_LENGTH) {
    throw new Error(`产品信息最多 ${PRODUCT_INFO_MAX_LENGTH} 个字符`);
  }
}
