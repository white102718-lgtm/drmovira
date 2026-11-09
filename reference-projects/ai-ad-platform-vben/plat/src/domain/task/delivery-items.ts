/** 投放明细；像素 ID 和令牌始终使用文本，同一投手可以承担多行。 */
export interface DeliveryTaskItem {
  type: string;
  platform: string;
  pixelName: string;
  pixelId: string;
  token: string;
  testCode: string;
  agencyLineName: string;
  agencyLineId?: string;
  /** 只用于展示历史渠道，不能作为代理线关联。 */
  channelName?: string;
  channelId?: string;
  deliveryUrl: string;
  operatorId: string;
  cloakUrl: string;
}

export const deliveryItemFields = [
  ['type', '类型', 50],
  ['platform', '投放平台', 100],
  ['pixelName', '像素名称', 200],
  ['pixelId', '像素 ID', 100],
  ['token', 'Token', 10000],
  ['testCode', '测试代码', 200],
  ['agencyLineName', '代理线', 80],
  ['deliveryUrl', '投放链接', 2000],
  ['operatorId', '投手 ID', 30],
  ['cloakUrl', '斗篷链接', 2000],
] as const;

const optionalDeliveryItemFields = new Set<keyof DeliveryTaskItem>([
  'cloakUrl',
  'pixelName',
  'type',
]);

export function isDeliveryItemFieldRequired(key: keyof DeliveryTaskItem) {
  return !optionalDeliveryItemFields.has(key);
}

/** 草稿允许缺字段，只有正式提交才调用此校验。 */
export function validateDeliveryItems(items: DeliveryTaskItem[]) {
  if (!items.length || items.length > 1000)
    return '请填写 1 至 1000 条投放明细';
  for (const [index, item] of items.entries()) {
    for (const [key, label, max] of deliveryItemFields) {
      const value = item[key]?.trim() ?? '';
      if (isDeliveryItemFieldRequired(key) && !value)
        return `第 ${index + 1} 行：请填写${label}`;
      if (value.length > max)
        return `第 ${index + 1} 行：${label}最多 ${max} 个字符`;
    }
    if (!/^\d+$/.test(item.operatorId))
      return `第 ${index + 1} 行：请选择有效投手`;
  }
  const names = new Set<string>();
  for (const item of items) {
    const name = item.agencyLineName.trim().toLowerCase();
    if (!names.add(name))
      return `同一任务中代理线不能重复：${item.agencyLineName.trim()}`;
  }
  return '';
}

export function emptyDeliveryItem(): DeliveryTaskItem {
  return {
    type: '',
    platform: '',
    pixelName: '',
    pixelId: '',
    token: '',
    testCode: '',
    agencyLineName: '',
    deliveryUrl: '',
    operatorId: '',
    cloakUrl: '',
  };
}

/** 合并所有包含有效表头的工作表；拒绝可能已丢失精度的数字 ID。 */
export function parseDeliveryWorkbook(
  workbook: import('xlsx').WorkBook,
  utils: typeof import('xlsx').utils,
): DeliveryTaskItem[] {
  const imported: DeliveryTaskItem[] = [];
  const normalize = (value: unknown) =>
    String(value ?? '')
      .replace(/[\s*]/g, '')
      .replace(/^代理线名称$/, '代理线')
      .toLowerCase();
  for (const name of workbook.SheetNames) {
    const sheet = workbook.Sheets[name];
    if (!sheet) continue;
    const rows = utils.sheet_to_json<Array<string | number>>(sheet, {
      header: 1,
      raw: true,
      defval: '',
    });
    const headerIndex = rows.findIndex((row) =>
      deliveryItemFields.every(
        ([key, label]) =>
          !isDeliveryItemFieldRequired(key) ||
          row.some(
            (cell) =>
              normalize(cell) === normalize(label) ||
              (key === 'operatorId' && normalize(cell) === '投手'),
          ),
      ),
    );
    const header = rows[headerIndex];
    if (!header) continue;
    for (const [index, row] of rows.slice(headerIndex + 1).entries()) {
      if (row.every((cell) => !String(cell).trim())) continue;
      const item = emptyDeliveryItem();
      for (const [key, label] of deliveryItemFields) {
        const column = header.findIndex(
          (cell) =>
            normalize(cell) === normalize(label) ||
            (key === 'operatorId' && normalize(cell) === '投手'),
        );
        const value = row[column] ?? '';
        if (key === 'pixelId' || key === 'operatorId') {
          if (
            typeof value === 'number' &&
            (!Number.isSafeInteger(value) || Math.abs(value) >= 1e15)
          ) {
            throw new Error(
              `${name} 第 ${headerIndex + index + 2} 行：${label}被保存为长数字，可能已丢失精度，请从原始数据复制完整 ID 并以文本填写`,
            );
          }
          if (
            typeof value === 'string' &&
            /^[+-]?\d+(?:\.\d+)?e[+-]?\d+$/i.test(value.trim())
          ) {
            throw new Error(
              `${name} 第 ${headerIndex + index + 2} 行：${label}为科学计数法，请从原始数据复制完整 ID 并以文本填写`,
            );
          }
        }
        item[key] = String(value).trim();
      }
      imported.push(item);
      if (imported.length > 1000) throw new Error('最多导入 1000 条明细');
    }
  }
  if (!imported.length) throw new Error('未找到明细，请使用模板中的完整表头');
  return imported;
}

/** 保留旧调用的精确匹配工具；新建与导入任务已不再调用。 */
export function matchDeliveryAgencyLines(
  items: DeliveryTaskItem[],
  agencyLines: Array<{
    cloakUrl: string;
    deliveryUrl: string;
    id: string;
    name: string;
    optimizerId: string;
    pixelId: string;
    pixelName: string;
    testCode: string;
    token: string;
    type: string;
  }>,
): DeliveryTaskItem[] {
  return items.map((item, index) => {
    const matches = agencyLines.filter(
      (line) => line.name.trim() === item.agencyLineName.trim(),
    );
    if (matches.length !== 1)
      throw new Error(
        `第 ${index + 1} 行：代理线“${item.agencyLineName}”${matches.length ? '存在重名，请手动选择' : '未匹配到系统代理线'}`,
      );
    return {
      ...item,
      agencyLineId: matches[0]!.id,
      agencyLineName: matches[0]!.name,
      cloakUrl: matches[0]!.cloakUrl,
      deliveryUrl: matches[0]!.deliveryUrl,
      operatorId: matches[0]!.optimizerId,
      pixelId: matches[0]!.pixelId,
      pixelName: matches[0]!.pixelName,
      testCode: matches[0]!.testCode,
      token: matches[0]!.token,
      type: matches[0]!.type,
    };
  });
}
