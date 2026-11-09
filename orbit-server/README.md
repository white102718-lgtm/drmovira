# ORBIT Python后台（全功能重新开发中）

采用现成 **RuoYi-FastAPI + MySQL8 + Redis** 底座，前端Vue3/Element Plus。直接替换Java后台框架，ORBIT业务在Python中重新开发；不把Java框架逐文件翻译成Python。

- [现行完整实施方案](docs/orbit/IMPLEMENTATION_PLAN.md)
- [开发、测试、验收逐项进度](docs/orbit/PROGRESS.md)
- [全部模块、页面与弹窗逻辑](docs/orbit/MODULE_LOGIC.md)
- [字段与条件清单](docs/orbit/FIELD_MATRIX.md)
- [框架替换及大数据量设计边界](docs/orbit/PYTHON_BACKEND_MIGRATION.md)

Python框架位于`python/ruoyi_fastapi`，ORBIT扩展位于`python/orbit_api`。上游为[insistence/RuoYi-FastAPI](https://github.com/insistence/RuoYi-FastAPI)，固定提交`7f7c66d373b6b344899961a42249ff51285cd865`，MIT许可证位于`python/ruoyi_fastapi/UPSTREAM_LICENSE`。

独立虚拟环境安装本仓库Python依赖及上游锁定依赖后，使用`tools/start-orbit.ps1`启动Python后台，默认独立18083端口。私有变量仅从指定`.env.local`的`ORBIT_PYTHON_`命名空间读取。初始化/升级数据库必须显式执行已审核迁移；应用启动不自动建表，不运行上游样例DROP SQL。

原Java代码、原SQL及旧回执保留作历史业务核对；现有18080/18081预览仍为旧Java实例，Python替换预览前不得因文件整理破坏该进程。主启动入口已改为Python，原启动器归入docs/orbit/history。

当前仅新Python框架基础HTTP检查通过，全部业务功能仍待逐项开发/测试/验收；旧Java的完成勾选与PASS不继承。性能需真实数据量验证，不以数据库名称或构建通过承诺容量。
