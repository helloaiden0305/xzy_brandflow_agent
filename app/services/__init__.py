"""
服务模块 - 提供 LLM 和传播素材生成服务
"""
from app.services.llm_service import llm_service, LLMUsageInfo, TopicsResponse, StreamResult

_image_service = None


def get_llm_service():
    """获取 LLM 服务实例"""
    return llm_service


def get_image_service():
    """懒加载传播素材服务实例，避免缺少图片 Key 时阻断基础服务启动"""
    global _image_service
    if _image_service is None:
        from app.services.image_service import ImageService

        _image_service = ImageService()
    return _image_service
