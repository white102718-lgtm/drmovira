/** 系统素材名称仅按换行拆分；逗号和空格属于名称内容，不作为分隔符。 */
export function parseMaterialNames(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/\r\n|\r|\n/)
        .map((name) => name.trim())
        .filter(Boolean),
    ),
  ];
}

export const MAX_MATERIAL_FILTER_NAMES = 200;
