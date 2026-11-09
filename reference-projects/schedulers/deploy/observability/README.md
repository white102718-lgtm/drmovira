在observability文件夹中执行
修改.env文件来改变生产和测试的ip
cp .env.prod .env
docker-compose -f docker-compose.yml up -d --build
完全停止和清理网络, 挂载卷等 docker-compose down -v, 仅在启动grafana后不能修改密码时使用
