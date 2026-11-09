/** 部门和负责人使用稳定 ID 匹配；名称只在唯一匹配时接受。 */
export interface ImportDepartment {
  id: string;
  deptName: string;
  status: number;
}

export interface ImportUser {
  id: string;
  displayName: string;
  realName?: null | string;
  username?: null | string;
  status: number;
}

/** 校验通过的一条分配，行号用于反馈原始表格位置。 */
export interface ImportedAllocation {
  line: number;
  team: string;
  teamName: string;
  assigneeId: string;
  assigneeName: string;
  pwaCount: number;
  h5Count: number;
}

function resolveUnique<T extends { id: string; status: number }>(
  input: string,
  items: T[],
  names: (item: T) => Array<null | string | undefined>,
  label: string,
): T {
  const byId = items.find((item) => item.id === input);
  const matches = byId
    ? [byId]
    : items.filter((item) => names(item).includes(input));
  if (matches.length !== 1) {
    throw new Error(
      matches.length ? `${label}重名，请填写 ID` : `${label}不存在`,
    );
  }
  const match = matches[0]!;
  if (match.status !== 1) throw new Error(`${label}已停用`);
  return match;
}

function lineCount(input: string, label: string) {
  if (!/^\d+$/.test(input)) throw new Error(`${label}必须为非负整数`);
  const value = Number(input);
  if (!Number.isSafeInteger(value) || value > 2_147_483_647) {
    throw new Error(`${label}过大`);
  }
  return value;
}

/** 解析 Excel 复制的四列 TSV，逐行报告问题；调用方必须在零错误时整批应用。 */
export function parseAllocationImport(
  text: string,
  departments: ImportDepartment[],
  users: ImportUser[],
  existingTeams: string[],
): { rows: ImportedAllocation[]; errors: string[] } {
  const rows: ImportedAllocation[] = [];
  const errors: string[] = [];
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/);
  const entries = lines
    .map((value, index) => ({ value, line: index + 1 }))
    .filter(({ value }) => value.trim());
  if (!entries.length) return { rows, errors: ['请先粘贴需要导入的表格数据'] };
  const header = entries[0]!.value.split('\t').map((cell) => cell.trim());
  if (
    ['部门', '部门名称或ID', '参与团队（部门）'].includes(header[0] ?? '') &&
    header[2] === 'PWA线路数' &&
    header[3] === 'H5线路数'
  )
    entries.shift();
  if (!entries.length) return { rows, errors: ['表头下方没有数据'] };
  if (entries.length > 200)
    return { rows, errors: ['一次最多导入 200 行，请分批导入'] };
  const used = new Set(existingTeams.filter(Boolean));
  for (const entry of entries) {
    try {
      const cells = entry.value.split('\t').map((cell) => cell.trim());
      if (cells.length !== 4)
        throw new Error(
          '需要四列：部门、负责人、PWA线路数、H5线路数，请从 Excel 复制单元格',
        );
      const [departmentValue, userValue, pwa, h5] = cells as [
        string,
        string,
        string,
        string,
      ];
      if (!departmentValue || !userValue)
        throw new Error('部门和负责人不能为空');
      const department = resolveUnique(
        departmentValue,
        departments,
        (item) => [item.deptName],
        '部门',
      );
      const user = resolveUnique(
        userValue,
        users,
        (item) => [item.displayName, item.realName, item.username],
        '负责人',
      );
      if (used.has(department.id))
        throw new Error('部门与当前分配或本次其他行重复');
      const pwaCount = lineCount(pwa, 'PWA线路数');
      const h5Count = lineCount(h5, 'H5线路数');
      // 后端使用 Java int 求和，避免单项合法但合计溢出。
      if (pwaCount + h5Count === 0 || pwaCount + h5Count > 2_147_483_647)
        throw new Error('线路数合计必须大于 0 且不超过 2147483647');
      used.add(department.id);
      rows.push({
        line: entry.line,
        team: department.id,
        teamName: department.deptName,
        assigneeId: user.id,
        assigneeName: user.displayName,
        pwaCount,
        h5Count,
      });
    } catch (error) {
      errors.push(
        `第 ${entry.line} 行：${error instanceof Error ? error.message : '数据无效'}`,
      );
    }
  }
  return { rows, errors };
}
