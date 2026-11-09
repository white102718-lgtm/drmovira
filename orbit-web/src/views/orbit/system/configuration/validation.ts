/** 前后端统一按NFC后的Unicode码点计数；不能用UTF-16的length截断合法emoji。 */
export function configurationTextError(value: unknown, maximum: number, required: boolean) {
  if (typeof value !== 'string') return '请输入文本'
  if (/[\p{Cc}\p{Cs}\u2028\u2029]/u.test(value)) return '不能包含控制字符或换行'
  const normalized = value.normalize('NFC').trim()
  if (required && !normalized) return '此项必填'
  if ([...normalized].length > maximum) return `最多${maximum}个字符`
  return ''
}

/** 凭据不trim和NFC变换；任何字符变换都可能改变认证内容。 */
export function configurationSecretError(value: unknown) {
  if (typeof value !== 'string' || !value) return '请输入新凭据'
  if (/[\p{Cc}\p{Cs}]/u.test(value)) return '凭据不能包含控制字符'
  if ([...value].length > 8192) return '凭据最多8192个字符'
  return ''
}
