# ORBIT 本地预览运行说明

2026-11-07 11:09（北京时间）已按用户要求启动并验证真实本地登录、getInfo和动态菜单。

- 前端：http://127.0.0.1:18081
- Java后端：http://127.0.0.1:18080
- 独立MySQL预览端口：13307；数据目录：D:/progress/orbit/.runtime/mysql-preview/data；库：orbit_preview。
- 独立Redis预览端口：16380；运行目录：D:/progress/orbit/.runtime/redis-preview。
- 预览状态和进程信息：D:/progress/orbit/.runtime/preview/status.json 及各实例process.id。
- 仅回环访问；后台进程保留供用户查看，不随自动测试停止。勿停止18080/18081/13307/16380，勿复用预览库跑测试或重做初始化。
- 凭据及独立生成的JWT/AES密钥仅存于用户指定的私有环境文件；不写入本文或仓库。未复用其他项目数据库或真实平台Token。
- 当前新增可见页为ORBIT工作台下的账户范围与系统配置；其他模块按台账仍待实施。账户目录为空，不用模拟业务数据冒充真实导入。
- 本地预览管理员密码由本聊天单独提供；captcha仅在独立预览库关闭，定时任务在该库停止，无真实广告或平台写入。

## 后续自动测试注意

MySQL测试仍用13306、Redis测试用16379。浏览器fixture现已隔离到18082，禁止复用18081预览。后端browser/network profile使用ruoyi-admin-it.jar，避免覆盖预览正在运行的默认JAR；已验证6项浏览器回归与预览并存。仍不得停止、迁移或重新初始化用户预览。新功能在独立测试库验证，当前预览保留启动时JAR和V013库。
