import sys
import os

# 添加子目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'comfyui-api-demo'))

# 导入Flask应用
from app import app

# Vercel需要这个
if __name__ == "__main__":
    app.run() 