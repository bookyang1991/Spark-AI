from flask import Flask, Response
from http.server import BaseHTTPRequestHandler

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return 'Flask应用成功部署到Vercel!' 

# 针对Vercel Serverless的处理函数
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write('Hello from Vercel Serverless Function!'.encode('utf-8'))
        return 