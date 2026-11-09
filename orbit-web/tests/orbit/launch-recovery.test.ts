import { afterEach, expect, it } from 'vitest'
import {
  cacheDraft,
  readDraftRecovery,
  cacheTemplateIntent,
  readTemplateIntent,
} from '@/api/orbit/launch-recovery'
import { newDraft } from '@/api/orbit/launch-form'
afterEach(() => sessionStorage.clear())
it('恢复缓存按实际账号隔离，不将同浏览器另一账号配置自动带入', () => {
  cacheDraft({
    actor: 'actor-a',
    body: newDraft({ owner_user_id: 'owner-a', owner_team_id: 'team-a' }),
    pendingKey: '1234567890123456',
  })
  expect(readDraftRecovery('actor-b')).toBeNull()
  expect(readDraftRecovery('actor-a')?.body.ownership.owner_user_id).toBe('owner-a')
})
it('模板操作仅保存受控业务描述和原键，CSRF在重试时重新取得', () => {
  cacheTemplateIntent({
    actor: 'actor-a',
    key: '1234567890123456',
    mutation: {
      kind: 'share',
      existing: { id: 'template', revision: 2 },
      recipients: ['owner-a'],
      reason: '明确分享',
    },
  })
  expect(readTemplateIntent('actor-b')).toBeNull()
  expect(readTemplateIntent('actor-a')?.mutation.kind).toBe('share')
  const raw = sessionStorage.getItem('orbit.launch.template-intent.v1.actor-a')!
  expect(raw).not.toMatch(/csrf|authorization|password/i)
})
