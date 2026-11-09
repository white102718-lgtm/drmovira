/** 将二维码 SDK 返回的临时码安全追加到后端生成的飞书 OAuth 地址。 */
export function appendFeishuTmpCode(gotoUrl: string, tmpCode: string) {
  const url = new URL(gotoUrl);
  url.searchParams.set('tmp_code', tmpCode);
  return url.toString();
}
