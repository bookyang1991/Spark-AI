# ============== 基础依赖 ==============
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import codecs
import logging
import base64
import random
import time
from datetime import datetime
from pathlib import Path
import sys

# ============== Flask应用初始化 ==============
app = Flask(__name__, static_url_path='', static_folder='static')
app.config['JSON_AS_ASCII'] = False
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST"]}})

# 添加根路由
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# ============== 全局配置 ==============
COMFYUI_URL = "http://localhost:8188"
COMFYUI_OUTPUT_DIR = Path(r"C:\SD\ComfyUI-aki-v1.3\output")
COMFYUI_MODEL_DIR = Path(r"C:\SD\ComfyUI-aki-v1.3\models")
WORKFLOW_FILE = "flux文生图.json"
MAX_QUEUE_SIZE = 5

# ============== 日志系统配置 ==============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("api.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ComfyUI-API")

# ============== 工作流加载与验证 ==============
def validate_workflow(workflow: dict):
    """验证工作流关键节点"""
    required_nodes = {
        "10": {"type": "UNETLoader", "inputs": ["unet_name"]},
        "11": {"type": "DualCLIPLoader", "inputs": ["clip_name1", "clip_name2"]},
        "12": {"type": "VAELoader", "inputs": ["vae_name"]},
        "14": {
            "type": "FluxSamplerParams+",
            "inputs": ["seed", "steps", "guidance", "max_shift", "base_shift", "denoise"]
        },
        "15": {"type": "EmptyLatentImage", "inputs": ["width", "height"]},
        "16": {"type": "VAEDecode", "inputs": ["samples", "vae"]},
        "17": {"type": "SaveImage", "inputs": ["images"]},
        "52": {"type": "TeaCache", "inputs": ["model"]},
        "54": {"type": "CLIPTextEncode", "inputs": ["text", "clip"]},
        "55": {"type": "Seed", "inputs": ["seed"]},
        "57": {"type": "Number to Text", "inputs": ["number"]}
    }
    
    for node_id, config in required_nodes.items():
        node = workflow.get(node_id)
        if not node:
            raise ValueError(f"缺失关键节点 {node_id}")
        if node["class_type"] != config["type"]:
            raise ValueError(f"节点 {node_id} 类型错误，应为 {config['type']}")
        for inp in config["inputs"]:
            if inp not in node.get("inputs", {}):
                raise ValueError(f"节点 {node_id} 缺少输入字段 '{inp}'")
                
        # 特殊验证Flux采样器参数
        if node_id == "14" and node["class_type"] == "FluxSamplerParams+":
            inputs = node.get("inputs", {})
            # 验证参数类型
            for param in ["steps", "guidance", "max_shift", "base_shift", "denoise"]:
                if param in inputs and not isinstance(inputs[param], str):
                    raise ValueError(f"节点 {node_id} 的 {param} 参数必须是字符串类型")
            # 验证seed参数是否为节点连接
            if "seed" in inputs and not isinstance(inputs["seed"], list):
                raise ValueError(f"节点 {node_id} 的 seed 参数必须是节点连接")
                    
    return True

def load_workflow():
    """加载并验证工作流模板"""
    try:
        current_dir = Path(__file__).parent
        json_path = current_dir / "flux文生图.json"  # 更新工作流文件名
        
        logger.info(f"加载工作流文件: {json_path}")
        
        with codecs.open(json_path, "r", encoding="utf-8-sig") as f:
            content = '\n'.join([line.split('//')[0].strip() for line in f])
            workflow = json.loads(content)
            
        validate_workflow(workflow)
        logger.info("工作流验证通过")
        return workflow
        
    except Exception as e:
        logger.critical(f"工作流加载失败: {str(e)}", exc_info=True)
        exit(1)

workflow_template = load_workflow()

# ============== 核心功能 ==============
def get_image_data(task_id: str, comfyui_data: dict) -> list:
    """获取图片数据（自动处理Base64填充）"""
    try:
        logger.info(f"[{task_id}] 开始处理图片数据")
        logger.info(f"[{task_id}] ComfyUI数据: {json.dumps(comfyui_data, indent=2)}")
        
        # 获取最新的输出节点
        outputs = comfyui_data.get("outputs", {})
        if not outputs:
            logger.error(f"[{task_id}] 无输出数据")
            raise ValueError("无输出数据")
            
        # 查找包含图片的输出节点
        output_node = None
        for node_id, node_data in outputs.items():
            if "images" in node_data:
                output_node = node_data
                logger.info(f"[{task_id}] 找到图片输出节点: {node_id}")
                break
                
        if not output_node:
            logger.error(f"[{task_id}] 未找到图片输出节点")
            raise ValueError("未找到图片输出节点")
            
        images = output_node.get("images", [])
        if not images:
            logger.error(f"[{task_id}] 无有效的图片输出数据")
            raise ValueError("无有效的图片输出数据")
        
        logger.info(f"[{task_id}] 找到 {len(images)} 张图片")
        result_images = []
        
        for i, img in enumerate(images):
            logger.info(f"[{task_id}] 处理第 {i+1} 张图片")
            if "base64" in img:
                base64_str = img["base64"]
                logger.info(f"[{task_id}] 从API获取Base64数据")
            else:
                filename = img.get("filename")
                if not filename:
                    logger.error(f"[{task_id}] 图片文件名无效")
                    raise ValueError("图片文件名无效")
                    
                file_path = COMFYUI_OUTPUT_DIR / filename
                logger.info(f"[{task_id}] 尝试读取文件: {file_path}")
                
                if not file_path.exists():
                    logger.error(f"[{task_id}] 图片文件不存在: {filename}")
                    raise ValueError(f"图片文件不存在: {filename}")
                    
                with open(file_path, "rb") as f:
                    base64_str = base64.b64encode(f.read()).decode('utf-8')
                    logger.info(f"[{task_id}] 从文件读取Base64数据成功")
            
            # 处理Base64填充
            padding = 4 - (len(base64_str) % 4)
            if padding != 4:
                base64_str += "=" * padding
                logger.info(f"[{task_id}] 添加Base64填充: {padding}个=")
                
            result_images.append(f"data:image/png;base64,{base64_str}")
            logger.info(f"[{task_id}] 第 {i+1} 张图片处理完成")
            
        logger.info(f"[{task_id}] 所有图片处理完成，共 {len(result_images)} 张")
        return result_images
        
    except Exception as e:
        logger.error(f"[{task_id}] 图片数据处理失败: {str(e)}", exc_info=True)
        raise

def prepare_workflow(data: dict) -> dict:
    """准备发送到ComfyUI的工作流数据"""
    try:
        # 深拷贝工作流模板
        workflow = json.loads(json.dumps(workflow_template))
        
        # 获取批量生成数量
        batch_count = int(data.get("batch_count", 1))
        if batch_count < 1:
            batch_count = 1
        elif batch_count > MAX_QUEUE_SIZE:
            batch_count = MAX_QUEUE_SIZE
            
        # 更新工作流参数
        workflow["54"]["inputs"]["text"] = data["prompt"].strip()
        
        # 更新种子相关节点
        workflow["55"]["inputs"]["seed"] = data.get("seed", random.randint(0, 0xFFFFFFFF))  # 使用传入的种子或生成新的
        workflow["57"]["inputs"]["number"] = ["55", 1]  # 连接Seed节点到Number to Text节点
        workflow["14"]["inputs"]["seed"] = ["57", 0]  # 连接Number to Text节点到FluxSamplerParams+节点
        
        # 更新其他参数
        workflow["14"]["inputs"]["steps"] = str(data.get("steps", 30))
        workflow["14"]["inputs"]["guidance"] = str(data.get("guidance", 3.5))
        workflow["14"]["inputs"]["max_shift"] = str(data.get("max_shift", 1.15))
        workflow["14"]["inputs"]["base_shift"] = str(data.get("base_shift", 0.5))
        workflow["14"]["inputs"]["denoise"] = str(data.get("denoise", 1.0))
        workflow["15"]["inputs"]["width"] = int(data.get("width", 512))
        workflow["15"]["inputs"]["height"] = int(data.get("height", 1024))
        workflow["15"]["inputs"]["batch_size"] = batch_count
        
        return workflow
        
    except (KeyError, ValueError) as e:
        logger.error(f"工作流参数准备失败: {str(e)}")
        raise ValueError(f"参数错误: {str(e)}")
    except Exception as e:
        logger.error(f"工作流准备失败: {str(e)}", exc_info=True)
        raise

# ============== API路由 ==============
@app.route("/generate", methods=["POST"])
def generate_handler():
    """处理生成请求"""
    try:
        logger.info("收到生成请求")
        start_time = datetime.now()

        # ==== 请求验证 ====
        if request.headers.get("Content-Type", "").lower() != "application/json":
            return jsonify({"error": "Content-Type必须为application/json"}), 400

        if not request.data:
            return jsonify({"error": "请求体不能为空"}), 400

        try:
            data = request.get_json(force=True)
        except Exception as e:
            logger.error(f"JSON解析失败: {str(e)}", exc_info=True)
            return jsonify({"error": "无效的JSON格式"}), 400

        if "prompt" not in data or not str(data["prompt"]).strip():
            return jsonify({"error": "参数prompt不能为空"}), 400

        # ==== 业务逻辑 ====
        # 生成随机种子
        seed = data.get("seed")
        if seed is None:
            seed = random.randint(0, 0xFFFFFFFF)
            
        workflow = prepare_workflow(data)
        
        try:
            queue = requests.get(f"{COMFYUI_URL}/queue", timeout=5).json()
            queue_size = len(queue.get("queue_running", [])) + len(queue.get("queue_pending", []))
            if queue_size >= MAX_QUEUE_SIZE:
                logger.warning(f"队列已满 ({queue_size}/{MAX_QUEUE_SIZE})")
                return jsonify({"error": "系统繁忙，请稍后重试"}), 503
        except Exception as e:
            logger.error(f"队列状态检查失败: {str(e)}")
            return jsonify({"error": "服务状态检查失败"}), 503

        try:
            response = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow},
                timeout=30
            )
            response.raise_for_status()
            task_id = response.json().get("prompt_id")
            
            if not task_id:
                raise ValueError("无效的任务ID响应")
                
            logger.info(f"[{task_id}] 任务提交成功 | 耗时: {(datetime.now()-start_time).total_seconds():.2f}s")
            time.sleep(1.5)
            return jsonify({
                "task_id": task_id,
                "seed": seed
            })
            
        except requests.exceptions.RequestException as e:
            logger.error(f"ComfyUI通信失败: {str(e)}")
            return jsonify({"error": "AI引擎服务异常"}), 503
            
    except Exception as e:
        logger.error("请求处理异常", exc_info=True)
        return jsonify({"error": "内部服务器错误"}), 500

@app.route("/result")
def result_handler():
    """查询生成结果"""
    try:
        task_id = request.args.get("task_id")
        if not task_id:
            logger.error("缺少task_id参数")
            return jsonify({"error": "需要提供task_id"}), 400
            
        # 添加请求标识，用于区分不同的请求
        request_id = request.args.get("_t", "unknown")
        logger.info(f"[{task_id}] 查询结果请求 (请求ID: {request_id})")
        start_time = datetime.now()
        
        # 清除请求缓存
        headers = {"Cache-Control": "no-cache"}
        history = requests.get(f"{COMFYUI_URL}/history/{task_id}", headers=headers, timeout=10).json()
        
        # 首先检查任务是否在历史记录中
        if task_id in history:
            try:
                logger.info(f"[{task_id}] 找到任务历史记录")
                images_base64 = get_image_data(task_id, history[task_id])
                
                # 确保images_base64是一个非空列表
                if not images_base64 or not isinstance(images_base64, list):
                    logger.warning(f"[{task_id}] 图片数据格式异常: {type(images_base64)}")
                    return jsonify({
                        "status": "completed",
                        "images": [],
                        "error_message": "图片数据格式异常"
                    })
                
                # 记录返回的图片数量
                logger.info(f"[{task_id}] 结果查询成功，返回{len(images_base64)}张图片 | 总耗时: {(datetime.now()-start_time).total_seconds():.2f}s")
                return jsonify({
                    "status": "completed",
                    "images": images_base64
                })
            except Exception as e:
                logger.error(f"[{task_id}] 图片处理失败: {str(e)}", exc_info=True)
                return jsonify({
                    "status": "completed",
                    "images": [],
                    "error_message": f"图片处理失败: {str(e)}"
                })
        else:
            # 检查任务是否在队列中
            queue = requests.get(f"{COMFYUI_URL}/queue").json()
            
            def extract_task_ids(queue_section):
                task_ids = []
                for task in queue_section:
                    if isinstance(task, dict):
                        for key in task:
                            task_data = task.get(str(key), {})
                            if isinstance(task_data, dict) and "task_id" in task_data:
                                task_ids.append(task_data["task_id"])
                return list(set(task_ids))
                
            running_ids = extract_task_ids(queue.get("queue_running", []))
            pending_ids = extract_task_ids(queue.get("queue_pending", []))
            
            if task_id in running_ids:
                logger.info(f"[{task_id}] 任务运行中")
                return jsonify({"status": "pending"})
            elif task_id in pending_ids:
                logger.info(f"[{task_id}] 任务排队中")
                return jsonify({"status": "pending"})
            else:
                # 任务不在队列中，也不在历史记录中
                # 尝试检查输出目录中是否有对应任务ID的图片文件
                try:
                    # 检查输出目录中是否有最近生成的图片
                    output_files = list(COMFYUI_OUTPUT_DIR.glob(f"*{task_id}*"))
                    if output_files:
                        logger.info(f"[{task_id}] 在输出目录找到相关文件: {len(output_files)}个")
                        # 构造一个模拟的history数据结构
                        mock_history = {
                            "outputs": {
                                "17": {
                                    "images": [{"filename": file.name} for file in output_files]
                                }
                            }
                        }
                        try:
                            images_base64 = get_image_data(task_id, mock_history)
                            logger.info(f"[{task_id}] 从输出目录成功读取{len(images_base64)}张图片")
                            return jsonify({
                                "status": "completed",
                                "images": images_base64
                            })
                        except Exception as e:
                            logger.error(f"[{task_id}] 从输出目录读取图片失败: {str(e)}", exc_info=True)
                    
                    # 如果任务刚刚完成但尚未写入历史记录，进行多次重试
                    logger.warning(f"[{task_id}] 任务未找到，开始重试获取历史记录")
                    # 增加重试次数和等待时间
                    max_retries = 3
                    retry_count = 0
                    retry_history = {}
                    
                    while retry_count < max_retries:
                        retry_count += 1
                        wait_time = 1.0 * retry_count  # 逐步增加等待时间
                        logger.info(f"[{task_id}] 重试 {retry_count}/{max_retries}，等待 {wait_time}秒")
                        time.sleep(wait_time)
                        
                        try:
                            retry_history = requests.get(f"{COMFYUI_URL}/history/{task_id}", timeout=10).json()
                            if task_id in retry_history:
                                logger.info(f"[{task_id}] 重试第{retry_count}次成功找到任务历史")
                                break
                        except Exception as e:
                            logger.error(f"[{task_id}] 重试获取历史记录失败: {str(e)}")
                            # 继续下一次重试
                    
                    # 处理重试结果
                    if task_id in retry_history:
                        logger.info(f"[{task_id}] 重试成功找到任务历史")
                        try:
                            images_base64 = get_image_data(task_id, retry_history[task_id])
                            if not images_base64 or not isinstance(images_base64, list):
                                logger.warning(f"[{task_id}] 重试后图片数据格式异常: {type(images_base64)}")
                                return jsonify({
                                    "status": "completed",
                                    "images": [],
                                    "error_message": "图片数据格式异常"
                                })
                                
                            logger.info(f"[{task_id}] 重试成功，返回{len(images_base64)}张图片")
                            return jsonify({
                                "status": "completed",
                                "images": images_base64
                            })
                        except Exception as e:
                            logger.error(f"[{task_id}] 重试处理图片失败: {str(e)}", exc_info=True)
                            return jsonify({
                                "status": "completed",
                                "images": [],
                                "error_message": f"图片处理失败: {str(e)}"
                            })
                    else:
                        logger.warning(f"[{task_id}] 多次重试后仍未找到任务")
                except Exception as e:
                    logger.error(f"[{task_id}] 额外检查过程出错: {str(e)}", exc_info=True)
                
                # 所有尝试都失败，返回任务不存在
                logger.warning(f"[{task_id}] 任务未找到")
                return jsonify({"error": "任务不存在或已过期"}), 404
                
    except requests.exceptions.RequestException as e:
        logger.error(f"[{task_id}] 查询失败: {str(e)}")
        return jsonify({"error": "查询服务不可用"}), 503
    except Exception as e:
        logger.error(f"[{task_id}] 结果处理异常", exc_info=True)
        return jsonify({"error": "内部服务器错误"}), 500

# ============== 服务启动 ==============
if __name__ == "__main__":
    try:
        logger.info("="*60)
        logger.info("启动服务前检查...")
        
        # 检查ComfyUI服务
        try:
            test_res = requests.get(f"{COMFYUI_URL}/history", timeout=10)
            if test_res.status_code != 200:
                logger.warning(f"ComfyUI服务未运行或无法访问 | 状态码: {test_res.status_code}")
                logger.warning("注意：图像生成功能将不可用，但Web界面可以正常访问")
        except Exception as e:
            logger.warning(f"无法连接到ComfyUI服务: {str(e)}")
            logger.warning("注意：图像生成功能将不可用，但Web界面可以正常访问")
            
        # 确保输出目录存在
        if not COMFYUI_OUTPUT_DIR.exists():
            COMFYUI_OUTPUT_DIR.mkdir(parents=True)
            logger.info(f"创建输出目录: {COMFYUI_OUTPUT_DIR}")
            
        logger.info("="*60)
        logger.info("服务启动成功！")
        logger.info(f"Web界面: http://localhost:5000")
        logger.info(f"API文档: http://localhost:5000/generate")
        logger.info("="*60)
        
        app.run(host='0.0.0.0', port=5000, debug=True)
        
    except Exception as e:
        logger.critical("启动失败", exc_info=True)
        exit(1)