# -*- coding: utf-8 -*-
from __future__ import absolute_import
import unittest
from pyes.tests import ESTestCase
from pyes.utils import clean_string, make_id
from pyes.es import ES

class UtilsTestCase(ESTestCase):
    def test_cleanstring(self):
        self.assertEqual(clean_string("senthil("), "senthil")
        self.assertEqual(clean_string("senthil&"), "senthil")
        self.assertEqual(clean_string("senthil-"), "senthil")
        self.assertEqual(clean_string("senthil:"), "senthil")

    def test_servers(self):
        # servers are now dicts with scheme, host, port
        geturls = lambda servers: ["{scheme}://{host}:{port}".format(**server) for server in servers]
        es = ES("127.0.0.1:9200")
        self.assertEqual(geturls(es.servers), ["http://127.0.0.1:9200"])
        es = ES(("http", "127.0.0.1", 9400))
        self.assertEqual(geturls(es.servers), ["http://127.0.0.1:9400"])

    def test_make_id(self):
        self.assertEqual(make_id("prova"), "GJu7sAxfT7e7qa2ShfGT0Q")

if __name__ == "__main__":
    unittest.main()
