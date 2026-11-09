# -*- coding:utf-8 -*-
# @Time : 2023/07/10
# @Author : York
# 解决多进程日志写入混乱问题
import os
import re
import sys
import time
from logging.handlers import TimedRotatingFileHandler


def posix_lock(file):
    f = open(file, "a")
    fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
    return f


if sys.platform.startswith("win"):
    lock = lambda x: None
elif sys.platform.startswith(("linux", "darwin")):
    import fcntl

    lock = posix_lock


class MyTimeRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def getFilesToDelete(self):
        dir_name = os.path.dirname(self.baseFilename)
        # 先转义字面量，再将所有 %X 格式符统一替换为 \w+
        # 如 %Y-%m-%d.log -> \w+-\w+-\w+\.log，自动适配任意 suffix 规则
        regex = "^" + re.sub(r"%[a-zA-Z]", r"\\w+", re.escape(self.suffix)) + "$"
        file_list = [
            os.path.join(dir_name, f)
            for f in os.listdir(dir_name)
            if re.match(regex, f)
        ]
        file_list.sort()
        if len(file_list) <= self.backupCount:
            return []
        return file_list[:len(file_list) - self.backupCount]

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        currentTime = int(time.time())
        dstNow = time.localtime(currentTime)[-1]
        t = self.rolloverAt - self.interval
        if self.utc:
            timeTuple = time.gmtime(t)
        else:
            timeTuple = time.localtime(t)
            dstThen = timeTuple[-1]
            if dstNow != dstThen:
                if dstNow:
                    addend = 3600
                else:
                    addend = -3600
                timeTuple = time.localtime(t + addend)
        path_part = os.path.dirname(self.baseFilename)
        dfn = os.path.join(path_part, time.strftime(self.suffix, timeTuple))
        if not os.path.exists(dfn):
            f = lock(self.baseFilename)
            if os.path.exists(self.baseFilename):
                self.rotate(self.baseFilename, dfn)
            if f is not None:
                f.close()
        if self.backupCount > 0:
            for s in self.getFilesToDelete():
                os.remove(s)
        if not self.delay:
            self.stream = self._open()
        newRolloverAt = self.computeRollover(currentTime)
        while newRolloverAt <= currentTime:
            newRolloverAt = newRolloverAt + self.interval
        if (self.when == "MIDNIGHT" or self.when.startswith("W")) and not self.utc:
            dstAtRollover = time.localtime(newRolloverAt)[-1]
            if dstNow != dstAtRollover:
                if not dstNow:
                    addend = -3600
                else:
                    addend = 3600
                newRolloverAt += addend
        self.rolloverAt = newRolloverAt
