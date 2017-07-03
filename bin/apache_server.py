#!/usr/bin/env python
#
# Copyright 2009 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import tornado.httpserver
import tornado.ioloop
import tornado.web
import os, sys

ROOT = os.path.dirname(os.path.dirname(__file__))

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Hello, world")

class DeleteHandler(tornado.web.RequestHandler):
    def get(self):
        id = self.get_argument("id", None) 
        self.write("delete")
        try:
            os.remove('%s/bin/static/data_%s.xml'%(ROOT, id))
        except:
            pass
class TracertHandler(tornado.web.RequestHandler):
    def get(self):
        ip = self.get_argument("ip", None) 
        for i in os.popen('tracert -n %s' % ip):
            self.write(i)
    
def main():
    settings = {
        "static_path": "%s/bin/static"%ROOT,
        "traceroute_path":"%s/bin/traceroute"%ROOT,
    }
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/delete", DeleteHandler),
        (r"/tracert", TracertHandler),
        (r"/(apple-touch-icon\.xml)", tornado.web.StaticFileHandler, dict(path=settings['static_path'])),
        (r"/traceroute/(.*)", tornado.web.StaticFileHandler, dict(path=settings['traceroute_path'])),
    ], **settings)
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8888)
    tornado.ioloop.IOLoop.instance().start()

def daemon():
    os.umask(0)
    
    pid = os.fork()        
    if pid > 0:
        sys.exit(0)
    
    os.setsid()
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    
    for i in range(1024):
        try:
            os.close(i)
        except:
            continue

    sys.stdin = open("/dev/null", "w+")
    sys.stdout = sys.stdin
    sys.stderr = sys.stdin
    
if __name__ == "__main__":
    daemon()
    main()
