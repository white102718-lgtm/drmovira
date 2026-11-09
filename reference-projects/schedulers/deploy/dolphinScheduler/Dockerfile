ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# 1. 安装你需要的插件 (例如 mysql)
# 注意：install-plugins.sh 会去远程下载，确保你的 Docker 宿主机能联网
RUN bash ./bin/install-plugins.sh 3.4.0

# 2. 依然需要手动把 MySQL JDBC 驱动考进去（官方插件不包含驱动）
COPY --chown=1001:1001 ./libs/mysql-connector-j-8.0.33.jar /opt/dolphinscheduler/libs/
COPY --chown=1001:1001 ./libs/mysql-connector-j-8.0.33.jar /opt/dolphinscheduler/plugins/datasource-plugins/
