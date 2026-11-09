# 数据库初始化工具

本工具用于初始化广告平台的MongoDB数据库，创建必要的集合和索引。
有的数据是单独创建的, 不在init_db.py中

## 功能说明

- 创建MongoDB集合
- 创建MongoDB索引
- 支持强制重建索引

## 使用方法

### 基本用法

```bash
# 进入后端项目根目录
cd backend

# 运行初始化脚本
python init_db.py
```

### 强制重建索引

如果需要强制重建所有索引（会先删除现有索引），可以使用`--force`参数：

```bash
python init_db.py --force
```
