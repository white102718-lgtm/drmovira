import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

/** 用实际Vue编译器发现类型检查无法覆盖的模板表达式加载错误。 */
describe('素材路由组件实际SFC编译', () => {
  for (const file of ['index.vue', 'MaterialUpload.vue', 'MaterialTaxonomy.vue']) {
    it(`${file}的脚本与模板均可编译`, () => {
      const filename = new URL('../../src/views/orbit/materials/' + file, import.meta.url)
      const parsed = parse(readFileSync(filename, 'utf8'), { filename: file })
      expect(parsed.errors).toEqual([])
      const script = compileScript(parsed.descriptor, { id: `material-${file}` })
      const template = compileTemplate({
        source: parsed.descriptor.template!.content,
        filename: file,
        id: `material-${file}`,
        compilerOptions: { bindingMetadata: script.bindings },
      })
      expect(template.errors).toEqual([])
    })
  }
})
