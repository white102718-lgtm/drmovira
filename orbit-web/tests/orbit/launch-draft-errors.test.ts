import { afterEach, expect, it, vi } from 'vitest'
import { launchApi } from '@/api/orbit/launch'
import { newDraft } from '@/api/orbit/launch-form'
const id = '00000000-0000-4000-8000-000000000001'
const field = {
  path: '/identity_bindings/0/page_id',
  code: 'LAUNCH_IDENTITY_UNAVAILABLE',
  message: '当前主页不可用',
  constraint: null,
}
afterEach(() => vi.unstubAllGlobals())
it('草稿保存保留真实422字段错误，不吞身份JSON Pointer', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: field.code,
          message: field.message,
          field_errors: [field],
          retryable: false,
          request_id: id,
        }),
        { status: 422 },
      ),
    ),
  )
  await expect(
    launchApi.save(newDraft({ owner_user_id: id, owner_team_id: id }), 'csrf', 'same-request-key'),
  ).rejects.toMatchObject({ status: 422, field_errors: [field] })
})
