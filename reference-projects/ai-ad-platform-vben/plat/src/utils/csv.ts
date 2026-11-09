function safeCell(value: unknown) {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[+=@-]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function downloadCsv(
  filename: string,
  rows: readonly (readonly unknown[])[],
) {
  const content = rows
    .map((row) => row.map((cell) => safeCell(cell)).join(','))
    .join('\r\n');
  const url = URL.createObjectURL(
    new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
