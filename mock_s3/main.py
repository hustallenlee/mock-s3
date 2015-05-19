#!/usr/bin/env python
#coding=utf-8
import argparse
import logging
import os
import sys
import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn

from actions import get_acl, get_item, list_buckets, ls_bucket
from file_store import FileStore
reload(sys)
sys.setdefaultencoding("utf-8")


logging.basicConfig(level=logging.INFO)

class S3Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse.urlparse(self.path)
        print 'get self.path',self.path
        qs = urlparse.parse_qs(parsed_path.query, True)
        print self.headers
        host = self.headers['host'].split(':')[0]
        path = parsed_path.path
        bucket_name = None
        item_name = None
        req_type = None

        mock_hostname = self.server.mock_hostname
        if host != mock_hostname and mock_hostname in host:
            idx = host.index(mock_hostname)
            bucket_name = host[:idx-1]

        if path == '/' and not bucket_name:
            req_type = 'list_buckets'

        else:
            if not bucket_name:
                bucket_name, sep, item_name = path.strip('/').partition('/')
            else:
                item_name = path.strip('/')

            if not bucket_name:
                req_type = 'list_buckets'
            elif not item_name:
                req_type = 'ls_bucket'
            else:
                if 'acl' in qs and qs['acl'] == '':
                    req_type = 'get_acl'
                else:
                    req_type = 'get'

        if req_type == 'list_buckets':
            list_buckets(self)

        elif req_type == 'ls_bucket':
            ls_bucket(self, bucket_name, qs)

        elif req_type == 'get_acl':
            get_acl(self)

        elif req_type == 'get':
            get_item(self, bucket_name, item_name)

        else:
            self.wfile.write('%s: [%s] %s' % (req_type, bucket_name, item_name))

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        return self.do_PUT()
        
    def do_PUT(self):
        print self.headers
        parsed_path = urlparse.urlparse(self.path)
        print 'put self.path',self.path
        print urlparse.urlunparse(parsed_path)
        qs = urlparse.parse_qs(parsed_path.query, True)
        
        #print 'copy_num ',int(qs["copy_num"][0])  
        #print 'strip_num ',int(qs["strip_num"][0])
        host = self.headers['host'].split(':')[0]
        print 'host',host
        path = parsed_path.path
        print 'path',path
        bucket_name = None
        item_name = None
        req_type = None

        mock_hostname = self.server.mock_hostname
        print 'mock_hostname',mock_hostname

        if host != mock_hostname and mock_hostname in host:
            idx = host.index(mock_hostname)
            bucket_name = host[:idx-1]
        #print 'bucket_name',bucket_name
        if path == '/' and bucket_name:
            req_type = 'create_bucket'

        else:
            if not bucket_name:
                bucket_name, sep, item_name = path.strip('/').partition('/')
            else:
                item_name = path.strip('/')

            if not item_name:
                req_type = 'create_bucket'
            else:
                if 'acl' in qs and qs['acl'] == '':
                    req_type = 'set_acl'
                else:
                    req_type = 'store'

        if 'x-amz-copy-source' in self.headers:
            copy_source = self.headers['x-amz-copy-source']
            src_bucket, sep, src_key = copy_source.partition('/')
            req_type = 'copy'

        if req_type == 'create_bucket':
            self.server.file_store.create_bucket(bucket_name)
            self.send_response(200)

        elif req_type == 'store':
            bucket = self.server.file_store.get_bucket(bucket_name)
            if not bucket:
                # TODO: creating bucket for now, probably should return error
                bucket = self.server.file_store.create_bucket(bucket_name)
            #print 'in main'
            if 'copy_num' in qs:
                try:
                    copy_num=int(qs["copy_num"][0])
                except:
                    copy_num=1
                
            else:
                copy_num=1
            
            if 'strip_num' in qs:
                try:
                    strip_num=int(qs["strip_num"][0])
                except:
                    strip_num=1
            else:
                strip_num=1
            
                
            item = self.server.file_store.store_item(bucket, item_name, self,copy_num=copy_num,strip_num=strip_num)
            self.send_response(200)
            self.send_header('Etag', '"%s"' % item.md5)

        elif req_type == 'copy':
            self.server.file_store.copy_item(src_bucket, src_key, bucket_name, item_name, self)
            # TODO: should be some xml here
            self.send_response(200)

        self.send_header('Content-Type', 'text/xml')
        self.end_headers()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    def set_file_store(self, file_store):
        self.file_store = file_store

    def set_mock_hostname(self, mock_hostname):
        self.mock_hostname = mock_hostname

    def set_pull_from_aws(self, pull_from_aws):
        self.pull_from_aws = pull_from_aws

    #def set_file_copy_num(self,file_copy_num):
    #    self.file_copy_num=file_copy_num

    #def set_file_strip_num(self,file_strip_num):
    #    self.file_strip_num=file_strip_num


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='A Mock-S3 server.')
    parser.add_argument('--hostname', dest='hostname', action='store',
                        default='',
                        help='Hostname to listen on.')
    parser.add_argument('--port', dest='port', action='store',
                        default=10001, type=int,
                        help='Port to run server on.')
    parser.add_argument('--root', dest='root', action='store',
                        default='%s/s3store' % os.environ['HOME'],
                        help='Defaults to $HOME/s3store.')
    parser.add_argument('--pull-from-aws', dest='pull_from_aws', action='store_true',
                        default=False,
                        help='Pull non-existent keys from aws.')
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.hostname, args.port), S3Handler)
    server.set_file_store(FileStore(args.root))
    server.set_mock_hostname(args.hostname)
    server.set_pull_from_aws(args.pull_from_aws)

    print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
