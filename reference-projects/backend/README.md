# 安装数据库
`sudo su root`

# mongodb
```shell
--- mkdir -p /opt/pvstore/data/mongodb/data
--- mkdir -p /opt/pvstore/data/mongodb/log
--- 启动
--- (cd deploy/mongo/ && docker-compose up -d)
--- 停止
--- (cd deploy/mongo/ && docker-compose down)
```

# minio
```shell
--- mkdir -p /opt/pvstore/data/minio
--- (cd deploy/minio && docker-compose up -d)
```

# postgres
```shell
--- mkdir -p /opt/postgresql/data
--- (cd deploy/postgres && docker-compose up -d)
```

# 环境要求

- Python 3.11

# 部署

docker-compose -f deploy/app/docker-compose.yml up -d --build

