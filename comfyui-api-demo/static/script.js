// 获取页面元素
const modal = document.getElementById('preview-modal');
const previewImage = document.getElementById('preview-image');
const resultSection = document.querySelector('.result-section');
const imageGrid = document.getElementById('image-grid');
const generateButton = document.getElementById('generate');
const clearButton = document.getElementById('clear');

// 记录当前分享的图片URL
let currentImageUrl = '';

// 页面加载时添加缓存和性能优化
document.addEventListener('DOMContentLoaded', function() {
    // 预连接到API服务器
    const linkElement = document.createElement('link');
    linkElement.rel = 'preconnect';
    linkElement.href = window.location.origin;
    document.head.appendChild(linkElement);
    
    // 为页面元素添加懒加载
    if ('loading' in HTMLImageElement.prototype) {
        // 浏览器支持懒加载
        document.querySelectorAll('img').forEach(img => {
            img.loading = 'lazy';
        });
    }
    
    // 添加事件监听
    generateButton.addEventListener('click', generateImage);
    clearButton.addEventListener('click', clearAll);
    
    // 点击模态框外部关闭
    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });
    
    // 注册安装事件（如果支持PWA）
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/service-worker.js')
                .then(reg => console.log('Service Worker registered'))
                .catch(err => console.log('Service Worker registration failed: ', err));
        });
    }
});

// 翻译中文到英文
async function translateToEnglish(text) {
    try {
        // 使用免费的翻译API
        const response = await fetch(`https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=zh|en`);
        const data = await response.json();
        
        if (data && data.responseData && data.responseData.translatedText) {
            console.log('翻译结果:', data.responseData.translatedText);
            return data.responseData.translatedText;
        } else {
            console.error('翻译失败:', data);
            return text; // 返回原文
        }
    } catch (error) {
        console.error('翻译服务错误:', error);
        return text; // 发生错误时返回原文
    }
}

// 生成图片
async function generateImage() {
    const prompt = document.getElementById('prompt').value.trim();
    if (!prompt) {
        alert('请输入描述文字');
        return;
    }

    // 获取选择的参数
    const aspectRatio = document.getElementById('aspect_ratio').value;
    
    // 根据比例设置宽高
    let width, height;
    switch (aspectRatio) {
        case '1:1':
            width = 512;
            height = 512;
            break;
        case '16:9':
            width = 1280;
            height = 720;
            break;
        case '9:16':
            width = 720;
            height = 1280;
            break;
        default:
            width = 512;
            height = 512;
    }

    // 获取风格参数，构建完整提示词
    const styleFormat = document.getElementById('style_format').value;
    const styleColor = document.getElementById('style_color').value;
    const styleLight = document.getElementById('style_light').value;
    const styleComposition = document.getElementById('style_composition').value;

    // 构建完整提示词
    let fullPrompt = prompt;
    if (styleFormat !== 'none') fullPrompt += `, ${styleFormat}`;
    if (styleColor !== 'none') fullPrompt += `, ${styleColor}`;
    if (styleLight !== 'none') fullPrompt += `, ${styleLight}`;
    if (styleComposition !== 'none') fullPrompt += `, ${styleComposition}`;

    // 首先显示结果区域
    resultSection.style.display = 'block';

    // 创建生成任务容器
    const generationTask = document.createElement('div');
    generationTask.className = 'generation-task';

    // 创建生成信息头部
    const generationHeader = document.createElement('div');
    generationHeader.className = 'generation-header';
    
    // 获取当前时间
    const now = new Date();
    const timeString = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).replace(/\//g, '/');

    // 设置生成信息内容
    generationHeader.innerHTML = `
        <div class="generation-prompt">生成: ${fullPrompt}</div>
        <div class="generation-time">${timeString}</div>
    `;
    
    // 创建图片网格
    const grid = document.createElement('div');
    grid.className = 'image-grid';

    // 创建4个加载中的缩略图
    const thumbnails = [];
    for (let i = 0; i < 4; i++) {
        const imageWrapper = document.createElement('div');
        imageWrapper.className = 'image-item';
        imageWrapper.innerHTML = `
            <div class="thumbnail-spinner"></div>
            <div class="thumbnail-time">预计时间：20 秒</div>
            <div class="skeleton" style="width: 100%; height: 150px; margin-top: 10px;"></div>
        `;
        grid.appendChild(imageWrapper);
        thumbnails.push(imageWrapper);
    }

    // 将头部和网格添加到任务容器
    generationTask.appendChild(generationHeader);
    generationTask.appendChild(grid);
    
    // 将任务容器添加到结果区域的最前面
    if (imageGrid.firstChild) {
        imageGrid.insertBefore(generationTask, imageGrid.firstChild);
    } else {
        imageGrid.appendChild(generationTask);
    }

    try {
        // 禁用生成按钮，防止重复点击
        generateButton.disabled = true;
        generateButton.textContent = '翻译并生成中...';
        
        // 翻译提示词（如果包含中文字符）
        let translatedPrompt = fullPrompt;
        if (/[\u4e00-\u9fa5]/.test(fullPrompt)) {
            translatedPrompt = await translateToEnglish(fullPrompt);
            console.log('原始提示词:', fullPrompt);
            console.log('翻译后提示词:', translatedPrompt);
            
            // 更新生成信息，显示翻译后的提示词
            const promptEl = generationHeader.querySelector('.generation-prompt');
            if (promptEl) {
                promptEl.innerHTML = `生成: ${fullPrompt}<br><span class="translated-prompt">翻译: ${translatedPrompt}</span>`;
            }
        }
        
        // 第一步：提交生成任务
        const generateResponse = await fetch('/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                prompt: translatedPrompt, // 使用翻译后的提示词
                seed: Math.floor(Math.random() * 0xFFFFFFFF),
                steps: 30,
                guidance: 3.5,
                max_shift: 1.15,
                base_shift: 0.5,
                denoise: 1.0,
                batch_count: 4,
                width: width,
                height: height
            })
        });

        const generateData = await generateResponse.json();
        console.log('生成任务响应:', generateData);

        if (generateData.error) {
            throw new Error(generateData.error);
        }

        // 第二步：轮询获取结果
        const taskId = generateData.task_id;
        let retries = 0;
        const maxRetries = 30;
        const startTime = Date.now();

        // 等待3秒再开始轮询
        await new Promise(resolve => setTimeout(resolve, 3000));

        while (retries < maxRetries) {
            try {
                const resultResponse = await fetch(`/result?task_id=${taskId}&_t=${Date.now()}`);
                const resultData = await resultResponse.json();
                console.log('轮询结果:', resultData);

                if (resultData.status === 'completed' && resultData.images && resultData.images.length > 0) {
                    // 逐个替换加载中的缩略图为实际图片
                    resultData.images.forEach((imageData, index) => {
                        const item = thumbnails[index];
                        if (item) {
                            const img = document.createElement('img');
                            img.src = imageData;
                            img.className = 'fade-in';
                            img.loading = 'lazy';
                            img.onclick = () => showModal(imageData);
                            item.innerHTML = '';
                            item.appendChild(img);
                        }
                    });
                    break;
                } else if (resultData.status === 'pending') {
                    // 更新状态文本
                    thumbnails.forEach(item => {
                        const timeEl = item.querySelector('.thumbnail-time');
                        if (resultData.progress) {
                            const progress = Math.round(resultData.progress * 100);
                            if (timeEl) {
                                timeEl.textContent = `生成中: ${progress}%`;
                            }
                        } else {
                            const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
                            const remainingSeconds = Math.max(1, 20 - elapsedSeconds);
                            if (timeEl) {
                                timeEl.textContent = `预计时间: ${remainingSeconds}秒`;
                            }
                        }
                    });
                } else if (resultData.error_message) {
                    throw new Error(resultData.error_message);
                }

                await new Promise(resolve => setTimeout(resolve, 2000));
                retries++;
            } catch (error) {
                console.error('轮询出错:', error);
                if (error.message.includes('任务不存在') || error.message.includes('已过期')) {
                    console.log('任务暂未就绪，继续等待...');
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    retries++;
                    continue;
                }
                throw error;
            }
        }

        if (retries >= maxRetries) {
            throw new Error('生成超时，请重试');
        }

    } catch (error) {
        console.error('生成失败:', error);
        alert('生成失败：' + error.message);
        // 移除生成任务容器
        generationTask.remove();
    } finally {
        // 恢复生成按钮状态
        generateButton.disabled = false;
        generateButton.textContent = '生成图片';
    }
}

// 显示图片预览
function showModal(imageSrc) {
    previewImage.src = imageSrc;
    currentImageUrl = imageSrc;
    modal.classList.add('active');
}

// 关闭预览
function closeModal() {
    modal.classList.remove('active');
}

// 下载图片
function downloadImage() {
    const link = document.createElement('a');
    link.href = previewImage.src;
    link.download = 'generated-image-' + new Date().getTime() + '.jpg';
    link.click();
}

// 分享图片
async function shareImage() {
    try {
        // 检查是否支持网页分享API
        if (navigator.share) {
            // 将图片转为Blob以便分享
            const response = await fetch(currentImageUrl);
            const blob = await response.blob();
            const file = new File([blob], 'ai-generated-image.jpg', { type: 'image/jpeg' });
            
            await navigator.share({
                title: 'AI生成的图片',
                text: '看看我用AI生成的这张图片！',
                files: [file]
            });
        } else {
            // 复制图片链接到剪贴板
            await navigator.clipboard.writeText(currentImageUrl);
            alert('图片链接已复制到剪贴板，您可以粘贴并分享！');
        }
    } catch (error) {
        console.error('分享失败:', error);
        alert('分享失败，请手动下载图片后分享');
    }
}

// 清除所有输入
function clearAll() {
    document.getElementById('prompt').value = '';
    document.getElementById('aspect_ratio').selectedIndex = 0;
    document.getElementById('style_format').selectedIndex = 0;
    document.getElementById('style_color').selectedIndex = 0;
    document.getElementById('style_light').selectedIndex = 0;
    document.getElementById('style_composition').selectedIndex = 0;
    resultSection.style.display = 'none';
} 