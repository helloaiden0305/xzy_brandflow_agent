"""
LLM 服务模块
使用火山引擎 Doubao API 进行 LLM 调用
支持流式输出和结构化输出
"""
import os
import re
from typing import List, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from pydantic import BaseModel, Field

load_dotenv()


def _get_pii_callback():
    """获取 PII 脱敏回调（延迟导入避免循环依赖）"""
    try:
        from app.core.callbacks import pii_callback
        return pii_callback
    except ImportError:
        return None


# ============== Pydantic 模型 ==============

class TopicItem(BaseModel):
    """单个宣传主题项"""
    title: str = Field(..., description="宣传主题标题")


class TopicsResponse(BaseModel):
    """宣传主题响应结构"""
    topics: List[TopicItem] = Field(..., description="生成的宣传主题列表")


@dataclass
class LLMUsageInfo:
    """LLM 调用的 token 使用信息"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


@dataclass
class StreamResult:
    """流式输出结果"""
    content: str = ""
    usage: LLMUsageInfo = field(default_factory=LLMUsageInfo)


class LLMService:
    """LLM 服务类 - 使用火山引擎 Doubao API"""
    
    # ============== Prompt 模板 ==============
    
    TOPIC_SYSTEM_PROMPT = """你是企业宣传内容策划顾问，熟悉品牌传播、内部公告、招聘宣传、技术成果宣传和活动复盘。

根据宣传方向生成5个适合企业内部审核与对外传播的候选宣传主题。

【主题策划原则】
1. 口径清晰：主题必须服务于企业形象、组织文化或业务成果表达。
2. 场景明确：适配品牌、HR、运营、行政或管理团队的常见宣传场景。
3. 信息可信：避免夸大承诺，优先突出事实、价值和受众收益。
4. 便于审核：标题应利于人工判断是否可发布、是否需要补充素材。
5. 可扩展：后续能自然展开为一篇结构完整的宣传内容。

【标题要求】
- 18字以内，清晰表达宣传主题
- 语气专业、稳健、积极
- 不使用夸张营销话术
- 避免敏感、绝对化和无法验证的表述"""

    ARTICLE_SYSTEM_PROMPT = """你是企业宣传内容写作顾问。

内容要求：
- 开头明确宣传背景、对象和核心信息
- 正文突出事实依据、业务价值、团队贡献或活动成果
- 语言专业、清晰、可信，适合发布前人工审核
- 结构清晰，使用 Markdown 小标题和分段
- 800-1200字
- 结尾给出面向员工、候选人、客户或合作伙伴的积极行动引导

直接输出 Markdown 格式宣传初稿。"""

    VISUAL_SYSTEM_PROMPT = """为AI图片生成工具提取3个传播素材描述。

格式要求：
- 纯视觉描述，含场景、色彩、风格
- 第一个为封面图，需清晰传达宣传主题
- 每行一个，不编号

风格：企业传播海报/简约现代/商务摄影/品牌视觉/活动纪实
禁止：文字内容、敏感政治暴力内容"""

    def __init__(self, enable_pii_anonymize: bool = True):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        
        # 模型配置
        self.model = os.getenv("LLM_MODEL", "doubao-seed-1-8-251228")
        self.model_fast = os.getenv("LLM_MODEL_FAST", "doubao-seed-1-6-flash-250828")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.temperature_fast = float(os.getenv("LLM_TEMPERATURE_FAST", "0.7"))
        self.temperature_extract = float(os.getenv("LLM_TEMPERATURE_EXTRACT", "0.4"))
        
        self.enable_pii_anonymize = enable_pii_anonymize
        self._llm = None
        self._llm_fast = None
        self._llm_extract = None
        
        print(f"[LLM] 模型配置: 标准={self.model}, 快速={self.model_fast}")
    
    def _get_callbacks(self) -> List:
        """获取回调列表"""
        if self.enable_pii_anonymize:
            pii_callback = _get_pii_callback()
            if pii_callback:
                return [pii_callback]
        return []
    
    def _create_llm(self, model: str, temperature: float) -> ChatOpenAI:
        """创建 LLM 客户端"""
        callbacks = self._get_callbacks()
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=self.api_key,
            base_url=self.base_url,
            callbacks=callbacks if callbacks else None,
        )
    
    @property
    def llm(self) -> ChatOpenAI:
        """标准 LLM（宣传初稿写作）"""
        if self._llm is None:
            self._llm = self._create_llm(self.model, self.temperature)
        return self._llm
    
    @property
    def llm_fast(self) -> ChatOpenAI:
        """快速 LLM（宣传主题生成）"""
        if self._llm_fast is None:
            self._llm_fast = self._create_llm(self.model_fast, self.temperature_fast)
        return self._llm_fast
    
    @property
    def llm_extract(self) -> ChatOpenAI:
        """提取用 LLM（低 temperature）"""
        if self._llm_extract is None:
            self._llm_extract = self._create_llm(self.model_fast, self.temperature_extract)
        return self._llm_extract
    
    def _extract_usage_info(self, response, model: str = "") -> LLMUsageInfo:
        """从 LLM 响应中提取 token 使用信息"""
        usage = LLMUsageInfo(model=model or self.model)
        
        if hasattr(response, 'response_metadata'):
            token_usage = response.response_metadata.get('token_usage', {})
            usage.input_tokens = token_usage.get('prompt_tokens', 0)
            usage.output_tokens = token_usage.get('completion_tokens', 0)
            usage.total_tokens = token_usage.get('total_tokens', 0)
        
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            usage.input_tokens = response.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = response.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = response.usage_metadata.get('total_tokens', usage.total_tokens)
        
        return usage
    
    def _update_usage_from_chunk(self, chunk: AIMessageChunk, usage: LLMUsageInfo) -> None:
        """从流式 chunk 更新 token 统计"""
        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
            usage.input_tokens = chunk.usage_metadata.get('input_tokens', usage.input_tokens)
            usage.output_tokens = chunk.usage_metadata.get('output_tokens', usage.output_tokens)
            usage.total_tokens = chunk.usage_metadata.get('total_tokens', usage.total_tokens)
        
        if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
            token_usage = chunk.response_metadata.get('token_usage', {})
            if token_usage:
                usage.input_tokens = token_usage.get('prompt_tokens', usage.input_tokens)
                usage.output_tokens = token_usage.get('completion_tokens', usage.output_tokens)
                usage.total_tokens = token_usage.get('total_tokens', usage.total_tokens)

    # ============== 核心方法 ==============

    async def plan_topics(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """根据宣传方向生成候选主题（结构化输出）"""
        messages = [
            SystemMessage(content=self.TOPIC_SYSTEM_PROMPT),
            HumanMessage(content=f"宣传方向：{topic_direction or '技术成果宣传'}")
        ]
        
        usage = LLMUsageInfo(model=self.model_fast)
        
        try:
            structured_llm = self.llm_fast.with_structured_output(TopicsResponse, include_raw=True)
            result = await structured_llm.ainvoke(messages)
            
            raw_response = result.get('raw')
            parsed_response = result.get('parsed')
            
            if raw_response:
                usage = self._extract_usage_info(raw_response, self.model_fast)
                
        except Exception as e:
            print(f"[LLM] 结构化输出失败，使用备用方案: {e}")
            return await self._plan_topics_fallback(topic_direction)
        
        return parsed_response or TopicsResponse(topics=[]), usage
    
    async def _plan_topics_fallback(self, topic_direction: str) -> Tuple[TopicsResponse, LLMUsageInfo]:
        """备用方案：手动解析 JSON"""
        import json
        
        system_prompt = self.TOPIC_SYSTEM_PROMPT + '\n\nJSON格式输出：{"topics":[{"title":"标题1"},...,{"title":"标题5"}]}'
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"宣传方向：{topic_direction or '技术成果宣传'}")
        ]
        
        response = await self.llm_fast.ainvoke(messages)
        usage = self._extract_usage_info(response, self.model_fast)
        
        try:
            content = response.content.strip()
            # 提取 JSON 部分
            if "```" in content:
                content = re.sub(r'^.*?```(?:json)?\s*', '', content, flags=re.DOTALL)
                content = re.sub(r'\s*```.*$', '', content, flags=re.DOTALL)
            
            json_start = content.find('{')
            json_end = content.rfind('}')
            if json_start != -1 and json_end != -1:
                content = content[json_start:json_end + 1]
            
            data = json.loads(content)
            return TopicsResponse(**data), usage
        except Exception as e:
            print(f"[LLM] JSON 解析失败: {e}")
            return TopicsResponse(topics=[]), usage
    
    async def write_draft(
        self,
        topic: str,
        feedback: str = "",
        revision_count: int = 0
    ) -> Tuple[str, LLMUsageInfo]:
        """生成宣传初稿（非流式）"""
        user_prompt = self._build_article_prompt(topic, feedback, revision_count)
        
        messages = [
            SystemMessage(content=self.ARTICLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        response = await self.llm.ainvoke(messages)
        usage = self._extract_usage_info(response)
        
        return response.content, usage

    async def stream_write_draft_with_usage(
        self,
        topic: str,
        feedback: str = "",
        revision_count: int = 0,
        on_chunk: Optional[Callable[[str], Any]] = None
    ) -> StreamResult:
        """流式生成宣传初稿（带 token 统计）"""
        user_prompt = self._build_article_prompt(topic, feedback, revision_count)
        
        messages = [
            SystemMessage(content=self.ARTICLE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        full_content = ""
        usage = LLMUsageInfo(model=self.model)
        
        async for chunk in self.llm.astream(messages):
            if isinstance(chunk, AIMessageChunk):
                if chunk.content:
                    full_content += chunk.content
                    if on_chunk:
                        on_chunk(chunk.content)
                self._update_usage_from_chunk(chunk, usage)
        
        # 估算 token（如果 API 未返回）
        if usage.total_tokens == 0:
            usage.input_tokens = len(self.ARTICLE_SYSTEM_PROMPT + user_prompt) // 2
            usage.output_tokens = len(full_content) // 2
            usage.total_tokens = usage.input_tokens + usage.output_tokens
        
        return StreamResult(content=full_content, usage=usage)
    
    async def extract_visual_points(self, article_content: str) -> Tuple[List[str], LLMUsageInfo]:
        """从宣传内容中提取视觉摘要"""
        truncated = article_content[:1500] if len(article_content) > 1500 else article_content
        
        messages = [
            SystemMessage(content=self.VISUAL_SYSTEM_PROMPT),
            HumanMessage(content=f"宣传内容：\n{truncated}")
        ]
        
        response = await self.llm_extract.ainvoke(messages)
        usage = self._extract_usage_info(response, self.model_fast)
        
        # 解析响应，清理编号前缀
        points = []
        for line in response.content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('-'):
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
                if cleaned:
                    points.append(cleaned)
        
        return points[:3], usage
    
    def _build_article_prompt(self, topic: str, feedback: str, revision_count: int) -> str:
        """构建宣传初稿生成的用户提示"""
        if feedback and revision_count > 0:
            return f"宣传主题：{topic}\n\n第{revision_count}次修订，修改意见：{feedback}\n\n请针对性修改。"
        return f"宣传主题：{topic}"


# 单例实例
llm_service = LLMService()
