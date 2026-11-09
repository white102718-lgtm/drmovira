import { test, expect } from '@playwright/test'
import path from 'node:path'

/** 真实登录、菜单、合同API与数据库；范围仅在独立fixture创建，不伪造响应。 */
test('审计菜单、详情、分页筛选和错误恢复', async ({ page }, info) => {
  const captcha = page.waitForResponse((r) => r.url().endsWith('/captchaImage'))
  await page.goto('/login')
  await captcha
  await page.getByPlaceholder('账号').fill('admin')
  await page.getByPlaceholder('密码').fill(process.env.ORBIT_E2E_FIXTURE_PASSWORD!)
  await page.getByRole('button', { name: '登 录' }).click()
  await expect(page).toHaveURL(/\/index$/)
  await page.evaluate(async () => {
    const cookie = document.cookie.split('; ').find((v) => v.startsWith('Admin-Token='))
    if (!cookie) throw new Error('Fixture登录缺少会话')
    const headers = {
      Authorization: `Bearer ${decodeURIComponent(cookie.slice('Admin-Token='.length))}`,
    }
    const base = '/dev-api/api/v1/scope-snapshots'
    const csrfReply = await fetch(`${base}/csrf`, { headers })
    if (!csrfReply.ok) throw new Error('Fixture CSRF失败')
    const csrf = (await csrfReply.json()).csrf_token
    for (let i = 0; i < 21; i++) {
      const reply = await fetch(base, {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
          'X-CSRF-Token': csrf,
        },
        body: JSON.stringify({
          mode: 'FILTER',
          account_ids: [],
          filter: {
            q: '',
            status: null,
            auth_status: null,
            operator_user_id: null,
            vendor_id: null,
          },
        }),
      })
      if (!reply.ok) throw new Error('Fixture范围创建失败')
    }
  })
  if (info.project.name === 'mobile-390') await page.locator('.hamburger-container').click()
  const sidebar = page.locator('.sidebar-container')
  await sidebar.getByText('ORBIT工作台', { exact: true }).click()
  await sidebar.getByText('ORBIT系统管理', { exact: true }).click()
  await sidebar.getByText('审计日志', { exact: true }).click()
  await expect(page.getByRole('heading', { name: '审计日志', exact: true })).toBeVisible()
  if (info.project.name === 'mobile-390')
    await page.locator('.drawer-bg').click({ position: { x: 380, y: 100 } })
  const pageSize = page.getByRole('combobox', { name: '每页条数' })
  await pageSize.focus()
  await pageSize.press('ArrowDown')
  await page.getByRole('option', { name: '20', exact: true }).click()
  const rows = page.locator('.el-table__body tbody tr')
  await expect(rows).toHaveCount(20)
  const first = await rows.first().locator('td').nth(6).innerText()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.getByText('第 2 页', { exact: true })).toBeVisible()
  await expect(rows.first().locator('td').nth(6)).not.toHaveText(first)
  await page.getByRole('button', { name: '上一页', exact: true }).click()
  await expect(page.getByText('第 1 页', { exact: true })).toBeVisible()
  await expect(rows.first().locator('td').nth(6)).toHaveText(first)
  await rows.first().getByRole('button', { name: '详情', exact: true }).click()
  const detail = page.getByRole('dialog', { name: '审计详情', exact: true })
  await expect(detail).toBeVisible()
  for (const label of [
    '审计UUID',
    '操作者UUID',
    '目标租户UUID',
    '对象UUID',
    '原因',
    '证据引用',
    '发生时间（UTC）',
    '请求UUID',
  ])
    await expect(detail.getByText(label, { exact: true })).toBeVisible()
  await expect(detail).toContainText(first)
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-audit-detail.png`),
    animations: 'disabled',
  })
  await page.keyboard.press('Escape')
  await expect(detail).toBeHidden()
  await page.getByLabel('动作代码', { exact: true }).fill('not-matching-audit')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByText('暂无符合条件的审计记录', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await expect(rows).toHaveCount(20)
  await page.getByLabel('操作者UUID', { exact: true }).fill('invalid-uuid')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('查询条件无效')
  await expect(rows).toHaveCount(20)
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByPlaceholder('开始日期', { exact: true }).fill('2026-11-06')
  await page.getByPlaceholder('开始日期', { exact: true }).press('Enter')
  await page.getByPlaceholder('结束日期', { exact: true }).fill('2026-11-06')
  await page.getByPlaceholder('结束日期', { exact: true }).press('Enter')
  await page.getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.getByText('暂无符合条件的审计记录', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await expect(rows).toHaveCount(20)
  await expect(page.locator('.el-loading-mask')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({
    path: path.join(process.env.ORBIT_E2E_OUTPUT!, `${info.project.name}-audit.png`),
    animations: 'disabled',
  })
})
