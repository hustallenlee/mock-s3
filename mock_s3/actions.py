import urllib2
import datetime
import random

import xml_templates


def list_buckets(handler):
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/xml')
    handler.end_headers()
    buckets = handler.server.file_store.buckets
    xml = ''
    for bucket in buckets:
        xml += xml_templates.buckets_bucket_xml.format(bucket=bucket)
    xml = xml_templates.buckets_xml.format(xml)
    handler.wfile.write(xml)


def ls_bucket(handler, bucket_name, qs):
    bucket = handler.server.file_store.get_bucket(bucket_name)
    if bucket:
        kwargs = {
            'marker': qs.get('marker', [''])[0],
            'prefix': qs.get('prefix', [''])[0],
            'max_keys': qs.get('max-keys', [1000])[0],
            'delimiter': qs.get('delimiter', [''])[0],
        }
        bucket_query = handler.server.file_store.get_all_keys(bucket, **kwargs)
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/xml')
        handler.end_headers()
        contents = ''
        for s3_item in bucket_query.matches:
            contents += xml_templates.bucket_query_content_xml.format(s3_item=s3_item)
        xml = xml_templates.bucket_query_xml.format(bucket_query=bucket_query, contents=contents)
        handler.wfile.write(xml)
    else:
        handler.send_response(404)
        handler.send_header('Content-Type', 'application/xml')
        handler.end_headers()
        xml = xml_templates.error_no_such_bucket_xml.format(name=bucket_name)
        handler.wfile.write(xml)


def get_acl(handler):
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/xml')
    handler.end_headers()
    handler.wfile.write(xml_templates.acl_xml)


def load_from_aws(handler, bucket_name, item_name):
    bucket = handler.server.file_store.get_bucket(bucket_name)
    aws_url = "http://s3.amazonaws.com/%s/%s" % (bucket_name, item_name)
    response = urllib2.urlopen(aws_url)
    data = response.read()
    response_headers = response.info()
    return handler.server.file_store.store_data(bucket, item_name, response_headers, data)


def get_item(handler, bucket_name, item_name):
    item = handler.server.file_store.get_item(bucket_name, item_name)
    if not item and handler.server.pull_from_aws:
            item = load_from_aws(handler, bucket_name, item_name)
    if not item:
        handler.send_response(404, '')
        return

    content_length = item.size

    headers = {}
    for key in handler.headers:
        headers[key.lower()] = handler.headers[key]

    if hasattr(item, 'creation_date'):
        last_modified = item.creation_date
    else:
        last_modified = item.modified_date
    last_modified = datetime.datetime.strptime(last_modified, '%Y-%m-%dT%H:%M:%S.000Z')
    last_modified = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')

    copy_selected=random.randint(0,item.copy_num-1)  #random select a copy
    if 'range' in headers:
        handler.send_response(206)
        handler.send_header('Content-Type', item.content_type)
        handler.send_header('Last-Modified', last_modified)
        handler.send_header('Etag', item.md5)
        handler.send_header('Accept-Ranges', 'bytes')
        ranges = handler.headers['bytes'].split('=')[1]
        start = int(ranges.split('-')[0])
        finish = int(ranges.split('-')[1])
        if finish == 0:
            finish = content_length - 1
        bytes_to_read = finish - start + 1
        handler.send_header('Content-Range', 'bytes %s-%s/%s' % (start, finish, content_length))
        handler.end_headers()

        strip_size=item.size/item.strip_num  #each strip size
        
        #begin strip number,begin offset
        start_strip_num=start/strip_size
        start_strip_offset=start%strip_size
        if start_strip_num==item.strip_num:
            start_strip_num=start_strip_num-1
            start_strip_offset=start_strip_offset+strip_size
        start_strip=(start_strip_num,start_strip_offset) 
        #finish strip number,finish offset
        finish_strip_num=finish/strip_size
        finish_strip_offset=finish%strip_size
        if finish_strip_num==item.strip_num:
            finish_strip_num=finish_strip_num-1
            finish_strip_offset=finish_strip_offset+strip_size
        finish_strip=(finish_strip_num,finish_strip_offset)
        
        for strip in range(0,handler.server.file_store.max_strip):
            with open(item.filename+'_'+str(strip)+'_'+str(copy_selected),'rb') as item.io:
                if start_strip[0]==strip and finish_strip[0]==strip:
                    item.io.seek(start_strip[1])
                    handler.wfile.write(item.io.read(finish_strip[1]-start_strip[1]))
                    return
                elif start_strip[0]==strip and finish_strip[0]>strip:
                    item.io.seek(start_strip[1])
                    handler.wfile.write(item.io.read(strip_size-start_strip[1]))
                
                elif strip>start_strip[0] and strip==finish_strip[0]:
                    handler.wfile.write(item.io.read(finish_strip[1]))
                    return
                elif strip>start_strip[0] and strip<finish_strip[0]:
                    handler.wfile.write(item.io.read(strip_size))
                else:
                    pass
                    
        return

    handler.send_response(200)
    handler.send_header('Last-Modified', last_modified)
    handler.send_header('Etag', item.md5)
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('Content-Type', item.content_type)
    handler.send_header('Content-Length', content_length)
    handler.end_headers()
    if handler.command == 'GET':
        for strip in range(0,item.strip_num):
            with open(item.filename+'_'+str(strip)+'_'+str(copy_selected),'rb') as item.io:
                handler.wfile.write(item.io.read())
         
