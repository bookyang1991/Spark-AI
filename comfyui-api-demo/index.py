from flask import Flask

# 创建一个简单的Flask应用来测试Vercel部署
app = Flask(__name__)

@app.route('/')
def home():
    return 'Flask应用成功部署到Vercel!'

# 这个是给Vercel用的
if __name__ == "__main__":
    app.run() 