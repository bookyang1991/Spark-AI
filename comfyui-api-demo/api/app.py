from flask import Flask, request, jsonify, send_from_directory
import os
import json
import base64
import requests
import random
import time
import uuid
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 任务存储（在生产环境中应使用数据库）
tasks = {}

# ComfyUI API端点
COMFY_API_HOST = os.environ.get("COMFY_API_HOST", "http://127.0.0.1:8188")

@app.route('/')
def index():
    # 在生产环境中，这里应重定向到static目录下的index.html
    return send_from_directory('../public', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('../public/static', path)

@app.route('/api/ping', methods=['GET'])
def ping():
    return jsonify({"status": "ok", "message": "API is running"}), 200

@app.route('/generate', methods=['POST'])
def generate_handler():
    try:
        # 获取请求数据
        data = request.json
        if not data:
            return jsonify({"error": "没有提供数据"}), 400

        # 必填字段
        required_fields = ["prompt", "width", "height"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"缺少'{field}'字段"}), 400

        # 提取参数
        prompt = data["prompt"]
        width = int(data["width"])
        height = int(data["height"])
        
        # 可选参数，设置默认值
        seed = data.get("seed", random.randint(0, 2**32 - 1))
        steps = int(data.get("steps", 30))
        guidance = float(data.get("guidance", 7.0))
        max_shift = float(data.get("max_shift", 1.0))
        base_shift = float(data.get("base_shift", 0.5))
        denoise = float(data.get("denoise", 1.0))
        batch_count = int(data.get("batch_count", 1))

        # 验证参数
        if not (128 <= width <= 2048) or not (128 <= height <= 2048):
            return jsonify({"error": "图像尺寸无效，宽度和高度必须在128到2048之间"}), 400

        # 创建任务ID
        task_id = str(uuid.uuid4())
        
        # 初始化任务状态
        tasks[task_id] = {
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "expires_at": time.time() + 3600,  # 1小时后过期
            "parameters": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "seed": seed,
                "steps": steps,
                "guidance": guidance,
                "max_shift": max_shift,
                "base_shift": base_shift,
                "denoise": denoise
            },
            "images": []
        }
        
        # 启动异步任务处理（在生产环境中应使用队列）
        # 这里模拟异步，实际上是立即处理
        try:
            process_image_generation(task_id)
        except Exception as e:
            logger.error(f"处理任务时出错: {str(e)}")
            # 不影响返回，因为这是异步的

        return jsonify({
            "task_id": task_id,
            "seed": seed,
            "status": "pending",
            "message": "图像生成任务已提交"
        }), 200

    except Exception as e:
        logger.error(f"生成处理错误: {str(e)}")
        return jsonify({"error": f"处理请求时出错: {str(e)}"}), 500

@app.route('/result', methods=['GET'])
def result_handler():
    task_id = request.args.get('task_id')
    
    if not task_id:
        return jsonify({"error_message": "未提供任务ID"}), 400
    
    if task_id not in tasks:
        return jsonify({"error_message": "任务不存在或已过期"}), 404
    
    task = tasks[task_id]
    
    # 检查任务是否过期
    if time.time() > task.get("expires_at", 0):
        tasks.pop(task_id, None)  # 删除过期任务
        return jsonify({"error_message": "任务不存在或已过期"}), 404
    
    return jsonify({
        "status": task["status"],
        "images": task.get("images", []),
        "progress": task.get("progress", 0)
    }), 200

def prepare_workflow(parameters):
    """准备ComfyUI工作流参数"""
    
    # 从参数中提取值
    prompt = parameters["prompt"]
    width = parameters["width"]
    height = parameters["height"]
    seed = str(parameters["seed"])  # 确保转为字符串
    steps = parameters["steps"]
    guidance = parameters["guidance"]
    max_shift = parameters["max_shift"]
    base_shift = parameters["base_shift"]
    denoise = parameters["denoise"]
    
    # 这里是示例工作流，实际应从文件加载或使用API查询
    workflow = {
        "1": {
            "inputs": {
                "text": prompt,
                "clip": ["14", 0]
            },
            "class_type": "CLIPTextEncode"
        },
        "2": {
            "inputs": {
                "text": "bad, deformed, nsfw",
                "clip": ["14", 0]
            },
            "class_type": "CLIPTextEncode"
        },
        "14": {
            "inputs": {
                "max_shift": max_shift,
                "base_shift": base_shift,
                "seed": ["55", 0],
                "steps": steps,
                "cfg": guidance,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "model": ["30", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0]
            },
            "class_type": "FluxSamplerParams+"
        },
        "3": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "30": {
            "inputs": {
                "ckpt_name": "realisticVisionV51_v51VAE.safetensors"
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "55": {
            "inputs": {
                "seed": int(seed)
            },
            "class_type": "Seed"
        },
        "57": {
            "inputs": {
                "value": ["55", 0]
            },
            "class_type": "NumberToText"
        },
        "6": {
            "inputs": {
                "samples": ["14", 0],
                "vae": ["30", 2]
            },
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {
                "filename_prefix": "ComfyUI",
                "images": ["6", 0]
            },
            "class_type": "SaveImage"
        }
    }
    
    return workflow

def process_image_generation(task_id):
    """处理图像生成任务"""
    
    if task_id not in tasks:
        logger.error(f"任务 {task_id} 不存在")
        return
    
    task = tasks[task_id]
    
    try:
        # 准备工作流
        workflow = prepare_workflow(task["parameters"])
        
        # 提交到ComfyUI服务器
        # 注意: 在Vercel上这个请求无法发送到本地服务器
        # 这里仅作示例，实际部署需要有公开可访问的ComfyUI服务
        response = requests.post(
            f"{COMFY_API_HOST}/api/prompt",
            json={
                "prompt": workflow
            }
        )
        
        if response.status_code != 200:
            logger.error(f"ComfyUI API请求失败: {response.status_code}, {response.text}")
            task["status"] = "error"
            task["error"] = f"API请求失败: {response.status_code}"
            return
        
        result = response.json()
        
        # 模拟生成过程（在实际环境中，我们会轮询ComfyUI API获取结果）
        # 在Vercel上这部分是不可能工作的，因为无法访问本地文件系统
        # 所以这里只是生成一些示例数据
        
        # 模拟进度更新
        for i in range(5):
            task["progress"] = (i+1) / 5
            time.sleep(1)  # 实际环境中不需要这个
        
        # 模拟生成的图像（base64编码）
        # 实际中这些应该从ComfyUI结果中获取
        sample_image_base64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAIAAADTED8xAAADMElEQVR4nOzVwQnAIBQFQYXff81RUkQCOyDj1YOPnbXWPmeTRef+/3O/OyBjzh3CD95BfqICMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMK0CMO0TAAD//2Anhf4QtqobAAAAAElFTkSuQmCC"
        
        # 更新任务状态
        task["status"] = "completed"
        task["images"] = [sample_image_base64]
        
    except Exception as e:
        logger.error(f"处理任务 {task_id} 时出错: {str(e)}")
        task["status"] = "error"
        task["error"] = str(e)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0') 