import base64
import mimetypes
from pathlib import Path
from typing import Any, AsyncGenerator, Coroutine, Dict, Generator, List, Optional, TypeVar, Union
import httpx
from openai import AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from app.tools.agent.common import run_sync

T = TypeVar('T')


class OpenAIClient:
    """
    OpenAI大模型调用封装类
    支持文件、图片、流式、异步等功能
    """

    def __init__(
            self,
            api_key: str,
            base_url: Optional[str] = None,
            proxy: Optional[str] = None,
            timeout: int = 60,
            max_retries: int = 3
    ):
        """
        初始化OpenAI客户端

        Args:
            api_key: OpenAI API密钥
            base_url: API基础URL，默认使用官方地址
            proxy: 代理地址，格式如 "http://proxy:port" 或 "socks5://proxy:port"
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.proxy = proxy
        self.timeout = timeout
        self.max_retries = max_retries

        # 配置HTTP客户端
        http_client_kwargs = {
            "timeout": timeout,
            "proxy": proxy
        }

        # 同步客户端
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            max_retries=max_retries,
            http_client=httpx.Client(**http_client_kwargs)
        )

        # 异步客户端
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            max_retries=max_retries,
            http_client=httpx.AsyncClient(**http_client_kwargs)
        )

    def encode_image(self, image_path: Union[str, Path]) -> str:
        """
        将图片文件编码为base64格式

        Args:
            image_path: 图片文件路径

        Returns:
            base64编码的图片数据URL
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        # 获取MIME类型
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type or not mime_type.startswith('image/'):
            raise ValueError(f"不支持的图片格式: {image_path.suffix}")

        # 读取并编码图片
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

        return f"data:{mime_type};base64,{encoded_image}"

    def read_file(self, file_path: Union[str, Path]) -> str:
        """
        读取文本文件内容

        Args:
            file_path: 文件路径

        Returns:
            文件内容
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            for encoding in ['gbk', 'gb2312', 'latin1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            raise ValueError(f"无法读取文件，编码格式不支持: {file_path}")

    def _build_messages(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None
    ) -> List[Dict[str, Any]]:
        """
        构建消息列表
        """
        if messages is None:
            messages = []

        # 添加系统提示
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        # 处理用户消息
        if prompt or images or files:
            user_content = []

            # 添加文本内容
            text_content = prompt or ""

            # 添加文件内容
            if files:
                for file_path in files:
                    file_content = self.read_file(file_path)
                    text_content += f"\n\n文件 {Path(file_path).name}:\n{file_content}"

            if text_content:
                user_content.append({"type": "text", "text": text_content})

            # 添加图片内容
            if images:
                for image_path in images:
                    image_data = self.encode_image(image_path)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": image_data}
                    })

            if user_content:
                messages.append({"role": "user", "content": user_content})

        return messages

    def chat(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None,
            **kwargs
    ) -> ChatCompletion:
        """
        同步聊天完成

        Args:
            messages: 消息历史
            prompt: 用户提示
            system_prompt: 系统提示
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            images: 图片文件路径列表
            files: 文本文件路径列表
            **kwargs: 其他参数

        Returns:
            聊天完成响应
        """
        messages = self._build_messages(
            messages=messages,
            prompt=prompt,
            system_prompt=system_prompt,
            images=images,
            files=files
        )

        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    async def achat(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None,
            **kwargs
    ) -> ChatCompletion:
        """
        异步聊天完成
        """
        messages = self._build_messages(
            messages=messages,
            prompt=prompt,
            system_prompt=system_prompt,
            images=images,
            files=files
        )

        return await self.async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    def chat_stream(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None,
            **kwargs
    ) -> Generator[ChatCompletionChunk, None, None]:
        """
        同步流式聊天完成

        Returns:
            流式响应生成器
        """
        messages = self._build_messages(
            messages=messages,
            prompt=prompt,
            system_prompt=system_prompt,
            images=images,
            files=files
        )

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )

        for chunk in stream:
            yield chunk

    async def achat_stream(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            model: str = "gpt-3.5-turbo",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None,
            **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        异步流式聊天完成

        Returns:
            异步流式响应生成器
        """
        messages = self._build_messages(
            messages=messages,
            prompt=prompt,
            system_prompt=system_prompt,
            images=images,
            files=files
        )

        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        )

        async for chunk in stream:
            yield chunk

    def get_response_text(self, response: ChatCompletion) -> str:
        """
        从响应中提取文本内容

        Args:
            response: 聊天完成响应

        Returns:
            响应文本
        """
        return response.choices[0].message.content or ""

    def get_reasoning_content(self, response: ChatCompletion) -> Optional[str]:
        """
        从响应中提取思考内容（仅支持思考的模型如o1系列）

        Args:
            response: 聊天完成响应

        Returns:
            思考内容，如果没有则返回None
        """
        try:
            # 获取第一个选择的消息
            message = response.choices[0].message

            # 检查是否有reasoning属性
            if hasattr(message, 'reasoning') and message.reasoning:
                return message.reasoning

            # 有些情况下reasoning可能在其他地方
            if hasattr(response, 'reasoning') and response.reasoning:
                return response.reasoning

            # 检查choices中是否有reasoning
            choice = response.choices[0]
            if hasattr(choice, 'reasoning') and choice.reasoning:
                return choice.reasoning

        except (AttributeError, IndexError, KeyError):
            pass

        return None

    def get_full_response_info(self, response: ChatCompletion) -> Dict[str, Any]:
        """
        获取完整的响应信息，包括思考内容

        Args:
            response: 聊天完成响应

        Returns:
            包含content、reasoning等信息的字典
        """
        result = {
            "content": self.get_response_text(response),
            "reasoning": self.get_reasoning_content(response),
            "model": response.model,
            "usage": response.usage.dict() if response.usage else None,
            "finish_reason": response.choices[0].finish_reason if response.choices else None
        }

        return result

    def get_stream_text(self, chunk: ChatCompletionChunk) -> str:
        """
        从流式响应块中提取文本内容

        Args:
            chunk: 流式响应块

        Returns:
            响应文本片段
        """
        if chunk.choices and chunk.choices[0].delta.content:
            return chunk.choices[0].delta.content
        return ""

    def get_stream_reasoning(self, chunk: ChatCompletionChunk) -> str:
        """
        从流式响应块中提取思考内容

        Args:
            chunk: 流式响应块

        Returns:
            思考内容片段
        """
        try:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta

                # 检查delta中是否有reasoning
                if hasattr(delta, 'reasoning') and delta.reasoning:
                    return delta.reasoning

        except (AttributeError, IndexError):
            pass

        return ""

    def get_stream_info(self, chunk: ChatCompletionChunk) -> Dict[str, Any]:
        """
        从流式响应块中提取完整信息

        Args:
            chunk: 流式响应块

        Returns:
            包含content、reasoning等信息的字典
        """
        return {
            "content": self.get_stream_text(chunk),
            "reasoning": self.get_stream_reasoning(chunk),
            "finish_reason": chunk.choices[0].finish_reason if chunk.choices else None,
            "model": getattr(chunk, 'model', None)
        }

    def chat_with_reasoning(
            self,
            messages: Optional[List[Dict[str, Any]]] = None,
            prompt: Optional[str] = None,
            system_prompt: Optional[str] = None,
            model: str = "o1-preview",  # 默认使用支持推理的模型
            temperature: Optional[float] = None,  # o1模型不支持temperature
            max_tokens: Optional[int] = None,
            images: Optional[List[Union[str, Path]]] = None,
            files: Optional[List[Union[str, Path]]] = None,
            **kwargs
    ) -> Dict[str, Any]:
        """
        专门用于带推理功能的模型调用

        Args:
            与chat方法相同，但默认模型为o1-preview

        Returns:
            包含推理内容的完整响应信息
        """
        # o1系列模型的特殊处理
        # if model.startswith('o1'):
        #     # o1模型不支持某些参数
        #     kwargs.pop('temperature', None)
        #     kwargs.pop('top_p', None)
        #     kwargs.pop('frequency_penalty', None)
        #     kwargs.pop('presence_penalty', None)
        #     temperature = None

        response = self.chat(
            messages=messages,
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            images=images,
            files=files,
            **kwargs
        )

        return self.get_full_response_info(response)
        """同步方式调用异步chat方法"""
        return run_sync(self.achat(**kwargs))

    def async_chat_stream(self, **kwargs) -> Generator[ChatCompletionChunk, None, None]:
        """同步方式调用异步stream方法"""

        async def _stream():
            results = []
            async for chunk in self.achat_stream(**kwargs):
                results.append(chunk)
            return results

        results = run_sync(_stream())
        for chunk in results:
            yield chunk

    def close(self):
        """关闭客户端连接"""
        if hasattr(self.client, 'close'):
            self.client.close()
        if hasattr(self.async_client, 'aclose'):
            run_sync(self.async_client.aclose())


# 使用示例
if __name__ == "__main__":
    # 初始化客户端
    client = OpenAIClient(
        api_key="your-api-key",
        base_url="https://api.openai.com/v1",  # 可以改为其他兼容的API地址
        proxy="http://proxy:port",  # 可选的代理设置
        timeout=60
    )

    # 示例1: 简单文本对话
    response = client.chat(prompt="你好，请介绍一下Python")
    print("回答:", client.get_response_text(response))

    # 示例2: 带系统提示的对话
    response = client.chat(
        system_prompt="你是一个专业的Python开发者",
        prompt="如何优化Python代码性能？"
    )
    print("回答:", client.get_response_text(response))

    # 示例3: 流式对话
    print("流式回答: ", end="")
    for chunk in client.chat_stream(prompt="请详细解释什么是机器学习"):
        content = client.get_stream_text(chunk)
        print(content, end="", flush=True)
    print()


    # 示例4: 异步调用
    async def async_example():
        response = await client.achat(prompt="异步调用测试")
        print("异步回答:", client.get_response_text(response))


    # 使用run_sync运行异步函数
    run_sync(async_example())

    # 示例5: 图片分析（需要支持视觉的模型）
    # response = client.chat(
    #     prompt="请分析这张图片",
    #     images=["path/to/image.jpg"],
    #     model="gpt-4-vision-preview"
    # )

    # 示例6: 文件内容分析
    # response = client.chat(
    #     prompt="请分析这个代码文件",
    #     files=["path/to/code.py"]
    # )

    # 示例7: 带思考功能的模型调用
    print("\n=== 思考模式示例 ===")

    # 使用o1模型进行复杂推理
    reasoning_response = client.chat_with_reasoning(
        prompt="请解决这个数学问题：一个班级有30个学生，其中60%是女生。如果新来了5个男生，现在女生占总人数的百分比是多少？请详细分析解题过程。",
        model="o1-preview"
    )

    print("推理过程:", reasoning_response.get("reasoning", "无推理内容"))
    print("最终答案:", reasoning_response.get("content", ""))
    print("使用的token:", reasoning_response.get("usage", {}))

    # 示例8: 普通模型对比
    normal_response = client.chat(
        prompt="请解决这个数学问题：一个班级有30个学生，其中60%是女生。如果新来了5个男生，现在女生占总人数的百分比是多少？",
        model="gpt-4"
    )

    print("\n普通模型回答:", client.get_response_text(normal_response))

    # 示例9: 流式调用中获取推理内容
    print("\n=== 流式推理示例 ===")
    reasoning_parts = []
    content_parts = []

    for chunk in client.chat_stream(
            prompt="分析量子计算的基本原理",
            model="o1-preview"
    ):
        chunk_info = client.get_stream_info(chunk)

        if chunk_info["reasoning"]:
            reasoning_parts.append(chunk_info["reasoning"])
            print(f"[思考]: {chunk_info['reasoning']}", end="")

        if chunk_info["content"]:
            content_parts.append(chunk_info["content"])
            print(f"[回答]: {chunk_info['content']}", end="")

    print(f"\n完整推理过程: {''.join(reasoning_parts)}")
    print(f"完整回答内容: {''.join(content_parts)}")
