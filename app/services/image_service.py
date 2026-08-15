"""
传播素材生成服务模块
使用 Gemini Image API 生成企业宣传传播素材
"""
import os
import asyncio
import base64
import uuid
import random
import httpx
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class ImageService:
    """传播素材生成服务类"""

    BRAND_STYLE_PROMPT = """请根据以下内容生成一张企业宣传传播素材：

【宣传内容】
{content}

【传播素材要求】
- 风格：现代企业品牌视觉，专业、可信、清晰
- 色调：明亮稳重，符合品牌传播、招聘宣传或内部公告场景
- 构图：简洁大气、留白得当、视觉重点突出
- 比例：3:4 竖版构图（适合移动端浏览）

【风格参考】
- 技术成果：现代办公空间、产品界面、数据看板、团队协作场景
- 招聘宣传：开放协作的办公环境、员工交流、专业成长氛围
- 活动复盘：会议、沙龙、团建或发布会的纪实感画面
- 内部公告：简洁品牌海报、温和光线、清晰视觉焦点
- 其他：根据宣传内容匹配最适合的企业传播风格

请生成一张高质量、有吸引力的传播素材。"""

    FALLBACK_PROMPTS = [
        "现代企业品牌传播海报，明亮办公室，团队协作，柔和自然光，3:4竖版构图",
        "企业技术成果宣传素材，数据看板和产品界面，简洁商务风格，3:4竖版构图",
        "企业内部公告视觉，简约现代品牌设计，清晰留白，稳重明亮色调，3:4竖版构图",
    ]

    def __init__(self):
        self.api_key = os.getenv("IMAGE_API_KEY", "")
        self.base_url = os.getenv("IMAGE_BASE_URL", "https://cn-beijing.yuannengai.com")
        self.model = os.getenv("IMAGE_MODEL", "gemini-3-pro-image-preview")
        
        self.image_dir = Path("static/images/generated")
        self.image_dir.mkdir(parents=True, exist_ok=True)

        if not self.api_key:
            raise ValueError("IMAGE_API_KEY 未配置")

    def _build_api_url(self) -> str:
        return f"{self.base_url}/v1beta/models/{self.model}:generateContent"

    def _save_image(self, image_base64: str, prefix: str = "brand") -> str:
        """保存 base64 传播素材到本地"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{prefix}_{timestamp}_{unique_id}.png"
        
        file_path = self.image_dir / filename
        with open(file_path, "wb") as f:
            f.write(base64.b64decode(image_base64))
        
        return f"/static/images/generated/{filename}"

    async def _call_gemini_api(self, prompt: str) -> Optional[str]:
        """调用 Gemini 传播素材生成 API"""
        url = self._build_api_url()
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                
                if "candidates" in result and result["candidates"]:
                    for part in result["candidates"][0]["content"]["parts"]:
                        if "inlineData" in part:
                            return part["inlineData"]["data"]
                
                print(f"[ImageService] API 响应中未找到传播素材数据")
                return None
                
        except httpx.HTTPStatusError as e:
            print(f"[ImageService] HTTP 错误: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"[ImageService] 请求异常: {e}")
            return None

    async def generate_single_image(
        self,
        prompt: str,
        optimize_for_brand: bool = True,
    ) -> Optional[str]:
        """生成单张传播素材（失败时使用备用提示词重试一次）"""
        current_prompt = self.BRAND_STYLE_PROMPT.format(content=prompt) if optimize_for_brand else prompt
        
        print(f"[ImageService] 生成传播素材: {prompt[:50]}...")
        
        # 首次尝试
        image_base64 = await self._call_gemini_api(current_prompt)
        if image_base64:
            image_path = self._save_image(image_base64)
            print(f"[ImageService] 传播素材生成成功: {image_path}")
            return image_path
        
        # 使用备用提示词重试
        print(f"[ImageService] 首次失败，使用备用提示词重试...")
        await asyncio.sleep(1)
        
        fallback_prompt = random.choice(self.FALLBACK_PROMPTS)
        image_base64 = await self._call_gemini_api(fallback_prompt)
        if image_base64:
            image_path = self._save_image(image_base64)
            print(f"[ImageService] 备用提示词成功: {image_path}")
            return image_path
        
        print(f"[ImageService] 传播素材生成失败，跳过")
        return None

    async def generate_images(
        self,
        visual_points: List[str],
        optimize_for_brand: bool = True,
    ) -> List[str]:
        """批量生成传播素材（并行）"""
        if not visual_points:
            return []

        tasks = [
            self.generate_single_image(prompt=point, optimize_for_brand=optimize_for_brand)
            for point in visual_points
        ]
        results = await asyncio.gather(*tasks)

        image_paths = [path for path in results if path is not None]
        print(f"[ImageService] 成功生成 {len(image_paths)}/{len(visual_points)} 张传播素材")
        return image_paths
