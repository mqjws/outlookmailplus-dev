"""业务编排层（services）。

目标：集中对外部系统（Graph/IMAP/临时邮箱 bridge）与业务回退编排（刷新、删除等）的逻辑，
routes 只负责参数校验与 HTTP 协议层适配。
"""
