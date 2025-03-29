from http.server import BaseHTTPRequestHandler
import json
import os
from app import app
from io import BytesIO
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response

def handle_request(event, context):
    """处理Vercel无服务器函数请求"""
    # 提取请求信息
    path = event.get('path', '/')
    http_method = event.get('httpMethod', 'GET')
    headers = event.get('headers', {})
    query_params = event.get('queryStringParameters', {}) or {}
    body = event.get('body', '')
    
    # 构建WSGI环境
    environ = {
        'wsgi.input': BytesIO(body.encode('utf-8') if isinstance(body, str) else body),
        'wsgi.errors': BytesIO(),
        'REQUEST_METHOD': http_method,
        'PATH_INFO': path,
        'QUERY_STRING': '&'.join([f"{k}={v}" for k, v in query_params.items()]),
        'CONTENT_TYPE': headers.get('content-type', ''),
        'CONTENT_LENGTH': headers.get('content-length', ''),
        'SERVER_NAME': 'vercel',
        'SERVER_PORT': '443',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': 'https',
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
    }
    
    # 添加HTTP头信息
    for key, value in headers.items():
        key = key.upper().replace('-', '_')
        if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            environ[f'HTTP_{key}'] = value
    
    # 处理响应
    response_data = {'statusCode': 500, 'body': '', 'headers': {}}
    
    def start_response(status, response_headers, exc_info=None):
        status_code = int(status.split(' ')[0])
        response_data['statusCode'] = status_code
        response_data['headers'] = dict(response_headers)
    
    # 调用Flask应用
    response_body = b''.join(app(environ, start_response))
    response_data['body'] = response_body.decode('utf-8')
    
    return response_data

# Vercel函数处理类
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # 模拟Lambda事件
        event = {
            'path': self.path,
            'httpMethod': 'GET',
            'headers': dict(self.headers),
            'queryStringParameters': {},
            'body': ''
        }
        
        # 处理请求
        response = handle_request(event, None)
        
        # 发送响应
        self.wfile.write(response['body'].encode('utf-8'))
        return
        
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        # 模拟Lambda事件
        event = {
            'path': self.path,
            'httpMethod': 'POST',
            'headers': dict(self.headers),
            'queryStringParameters': {},
            'body': post_data
        }
        
        # 处理请求
        response = handle_request(event, None)
        
        # 发送响应
        self.wfile.write(response['body'].encode('utf-8')) 