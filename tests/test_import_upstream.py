"""import-upstream.py 的测试。

这个仓库的说明是「会自检的小脚本」，而它的 CI 原先只有一句
`python -m py_compile import-upstream.py` —— 一个连 import 都不会执行的
检查。语法正确和「校验逻辑是对的」之间隔着整个 README。

校验逻辑是这个工具的全部价值：它宣称每个 blob 落盘前都用 Git 的 SHA-1
校验过，「A mismatch is a failure, not a warning」。如果那个哈希算错了，
6407 个文件、零失败这句话就什么都不是 —— 而且不会有任何症状。

所以这里拿 **git 自己** 当裁判：同样的内容让 `git hash-object` 算一遍，
和 blob_sha 的结果比。用另一个独立实现来验，比自己写一遍期望值可靠得多。

只用标准库。这个仓库的卖点之一就是零依赖，为了跑测试去装 pytest
会让那句话变虚。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_script():
    spec = importlib.util.spec_from_file_location(
        "import_upstream", ROOT / "import-upstream.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_upstream"] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


def git_hash_object(data: bytes) -> str:
    """让 git 自己算一遍，作为独立裁判。"""
    result = subprocess.run(
        ["git", "hash-object", "--stdin"],
        input=data, capture_output=True, check=True)
    return result.stdout.decode().strip()


class BlobShaMatchesGit(unittest.TestCase):
    """blob_sha 必须和 git hash-object 逐字节一致。"""

    CASES = {
        "空文件": b"",
        "一行 ASCII": b"hello\n",
        "没有结尾换行": b"hello",
        "中文 UTF-8": "第一行\n第二行\n".encode("utf-8"),
        "含 NUL 的二进制": b"\x00\x01\x02\xff\xfe",
        "内嵌 blob 头的内容": b"blob 5\x00hello",   # 前缀拼接写错就会在这里露馅
        "长内容": b"x" * 100_000,
        "CRLF": b"line1\r\nline2\r\n",
    }

    def test_every_case_matches(self):
        for label, data in self.CASES.items():
            with self.subTest(label):
                self.assertEqual(script.blob_sha(data), git_hash_object(data))

    def test_the_known_empty_blob(self):
        """空 blob 的 SHA 是 Git 里最出名的那个常量，写死一次做双保险。"""
        self.assertEqual(script.blob_sha(b""),
                         "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")

    def test_size_prefix_actually_participates(self):
        """漏掉 `blob <size>\\0` 前缀的话，结果会退化成普通 sha1。

        这是最容易写错、又最不容易被发现的一处：普通 sha1 也是 40 位十六进制，
        看起来完全正常，只是和 GitHub 给的 SHA 永远对不上。
        """
        import hashlib

        data = b"hello\n"
        self.assertNotEqual(script.blob_sha(data), hashlib.sha1(data).hexdigest())

    def test_a_single_byte_change_changes_the_hash(self):
        """截断或损坏必须被发现——这正是这个工具存在的理由。"""
        self.assertNotEqual(script.blob_sha(b"hello\n"), script.blob_sha(b"hellp\n"))
        # CDN 给出截断响应是真实发生过的场景
        full = b"x" * 1000
        self.assertNotEqual(script.blob_sha(full), script.blob_sha(full[:999]))


class WriteMode(unittest.TestCase):
    def test_executable_bit_is_set_for_100755(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "run.sh")
            script.write_mode(dest, b"#!/bin/sh\n", "100755")
            self.assertTrue(os.access(dest, os.X_OK), "100755 的文件必须可执行")

    def test_plain_file_is_not_made_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "notes.txt")
            script.write_mode(dest, b"hello\n", "100644")
            self.assertFalse(os.access(dest, os.X_OK), "普通文件不该带执行位")

    def test_contents_are_written_verbatim(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "bin")
            data = b"\x00\x01\xff\n"
            script.write_mode(dest, data, "100644")
            self.assertEqual(Path(dest).read_bytes(), data)


class Configuration(unittest.TestCase):
    """别人 clone 下来就能跑，不该被我本机的设置绊住。"""

    def test_proxy_is_not_hardcoded(self):
        self.assertEqual(
            script.PROXY, os.environ.get("UPSTREAM_PROXY", ""),
            "代理必须来自环境变量。写死成本机端口的话，别人跑起来每个请求都会"
            "连到一个不存在的本地端口，而错误信息里看不出跟代理有关。",
        )

    def test_no_proxy_means_respect_the_environment(self):
        """不设 UPSTREAM_PROXY 时，只能使用系统环境里的代理，不能自带一个。

        第一版断言「opener.handlers 里必须有 ProxyHandler」。那在我这台
        配了系统代理的机器上成立，在 CI runner 上不成立 —— urllib 的
        add_handler 只会收录带 *_open 方法的处理器，而 ProxyHandler 的
        方法是按每个代理动态生成的：一个代理都没有，它就没有方法，
        于是压根不会出现在 handlers 里。

        测试又一次编码了一个只在我这儿为真的前提。改成问真正该问的问题：
        这个 opener 会不会强塞一个我们自己写死的代理。
        """
        original = script.PROXY
        script.PROXY = ""
        try:
            opener = script.proxy_opener()
            installed = [handler.proxies for handler in opener.handlers
                         if type(handler).__name__ == "ProxyHandler"]
        finally:
            script.PROXY = original

        for proxies in installed:
            self.assertEqual(
                proxies, urllib.request.getproxies(),
                "不设 UPSTREAM_PROXY 时，代理只能来自系统环境",
            )

    def test_an_explicit_proxy_is_actually_used(self):
        """设了 UPSTREAM_PROXY 就必须真的走它，否则这个开关是假的。"""
        original = script.PROXY
        script.PROXY = "http://proxy.invalid:9999"
        try:
            opener = script.proxy_opener()
            handlers = [handler for handler in opener.handlers
                        if type(handler).__name__ == "ProxyHandler"]
            self.assertTrue(handlers, "显式设了代理，就该装上 ProxyHandler")
            self.assertEqual(handlers[0].proxies.get("http"),
                             "http://proxy.invalid:9999")
            self.assertEqual(handlers[0].proxies.get("https"),
                             "http://proxy.invalid:9999")
        finally:
            script.PROXY = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
