# -*- coding: utf-8 -*-
import logging

from env_vault.env_conf import MongodbConf, MinioConf, DorisConf, Redis, ErpMySQLConf, Env, env, _get_bool

logging.warning(f"deploy_env:[{env}]")
