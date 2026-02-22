# -*- coding: utf-8 -*-
"""SSL 绕过上下文管理器

提供统一的 SSL 验证绕过机制，供模型下载等场景使用。
使用 with 语句确保退出时自动恢复所有全局状态。
"""
import os
import ssl
from contextlib import contextmanager
from typing import Generator


@contextmanager
def ssl_bypass_context(disable: bool = True) -> Generator[None, None, None]:
    """SSL 证书验证绕过上下文管理器

    在 with 块中临时禁用 SSL 验证，退出时自动恢复。

    Args:
        disable: 是否禁用 SSL 验证。为 False 时直接 yield 不做任何操作。
    """
    if not disable:
        yield
        return

    saved_env = {}
    saved_ssl_context = None
    saved_httpx_init = None

    try:
        # 1. 保存并设置环境变量
        ssl_env_vars = ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE")
        for var in ssl_env_vars:
            saved_env[var] = os.environ.get(var)
            os.environ[var] = ""
        os.environ["HF_HUB_DISABLE_SSL_VERIFY"] = "1"
        os.environ["HF_HUB_DISABLE_SSL"] = "1"

        # 2. Patch ssl 模块
        saved_ssl_context = ssl._create_default_https_context
        ssl._create_default_https_context = ssl._create_unverified_context

        # 3. 禁用 urllib3 警告
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass

        # 4. Patch httpx (huggingface_hub >= 1.x 使用 httpx)
        try:
            import httpx
            saved_httpx_init = httpx.Client.__init__
            _orig_httpx_init = saved_httpx_init

            def _patched_httpx_init(self_client, *args, **kwargs):
                kwargs["verify"] = False
                return _orig_httpx_init(self_client, *args, **kwargs)

            httpx.Client.__init__ = _patched_httpx_init
        except ImportError:
            pass

        # 5. 清除已缓存的 HF session
        try:
            from huggingface_hub import close_session
            close_session()
        except ImportError:
            pass

        yield

    finally:
        # 恢复环境变量
        for var in ("CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
            old_val = saved_env.get(var)
            if old_val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = old_val
        os.environ.pop("HF_HUB_DISABLE_SSL_VERIFY", None)
        os.environ.pop("HF_HUB_DISABLE_SSL", None)

        # 恢复 ssl 上下文
        if saved_ssl_context is not None:
            ssl._create_default_https_context = saved_ssl_context

        # 恢复 httpx
        if saved_httpx_init is not None:
            try:
                import httpx
                httpx.Client.__init__ = saved_httpx_init
            except ImportError:
                pass


@contextmanager
def patched_requests_verify() -> Generator[None, None, None]:
    """Patch requests.Session.request 强制 verify=False

    单独提供此上下文管理器，用于需要 patch requests 库的场景。
    """
    import requests
    _orig_request = requests.Session.request

    def _patched_request(self, method, url, *args, **kwargs):
        kwargs["verify"] = False
        return _orig_request(self, method, url, *args, **kwargs)

    requests.Session.request = _patched_request
    try:
        yield
    finally:
        requests.Session.request = _orig_request
