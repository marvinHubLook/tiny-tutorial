import os
from pathlib import Path
from typing import Union, List, Optional
from tenacity import retry, stop_after_attempt, wait_fixed
from pydantic import BaseModel, Field
from app.utils.logger import getLogger
from app.tools.agent.openai_agent import OpenAIClient

logger = getLogger(__name__)

from app.tools.agent.models import (
    SCoTModelType,
    DEFAULT_SCOT_MODEL,
    THINKING_BUDGET_MODELS,
)
from app.tools.agent.common import extract_first_json_block, run_sync
from app.tools.agent.reasoner import _Reasoner

SYSTEM_INSTRUCTIONS = """
Thinking step-by-step：
	1. Identify challenge prompt about the Challenge Image,Find all possible
	2. Identify the classification, color, relative distance and coordinates of each item in the image,Approximate rotation angle
	3. coordinates Based on the plane rectangular coordinate system,Position in rectangular coordinates; Spatial position is based on the distance of spatial coordinates;Rotation angle relative to the front [0-90]
	4. Object categories: [sphere, cone, polyhedron, cylinder, cube, number, letter];Color categories: [green, red, gray, yellow, blue];Spatial position: [front, middle, back]
	5. Object categories If it is a number or letter, the specific content needs to be returned
    6. Find the correct answer based on {prompt} and answer it correctly or not

Finally, solve the challenge, locate the object, output the coordinates of the correct answer as json. Follow the following format to return a coordinates wrapped with a json code block:
```json
[
  {
    "bounding_box": {
      "start_point": {"x": x1, "y": y1},
      "end_point": {"x": x2, "y": y2}
    },
    "category": "category_name",
    "content": "specific_content_if_applicable",
    "color": "color_name",
    "position": "position_name",
    "rotation": "rotation",
    "result": result boolean
  },
  {
    "bounding_box": {
      "start_point": {"x": x1, "y": y1},
      "end_point": {"x": x2, "y": y2}
    },
    "category": "category_name",
    "content": "specific_content_if_applicable",
    "color": "color_name",
    "position": "position_name",
   "rotation": "rotation",
   "result": result boolean
  }
]
```
"""


class PointCoordinate(BaseModel):
    x: int
    y: int


class SpatialPath(BaseModel):
    start_point: PointCoordinate
    end_point: PointCoordinate


class ImageObjectArea(BaseModel):
    bounding_box: SpatialPath
    category: str
    content: str
    color: str
    position: str
    rotation: str
    result: bool


class SpatialBboxReasoner(_Reasoner[SCoTModelType]):

    def __init__(
            self,
            gemini_api_url: str,
            gemini_api_key: str,
            model: SCoTModelType = DEFAULT_SCOT_MODEL,
            constraint_response_schema: bool = False,
    ):
        super().__init__(gemini_api_url, gemini_api_key, model, constraint_response_schema)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(3),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry request ({retry_state.attempt_number}/2) - Wait 3 seconds - Exception: {retry_state.outcome.exception()}"
        ),
    )
    async def invoke_async(
            self,
            image: Union[str, Path, os.PathLike],
            **kwargs,
    ) -> List:
        client = None
        try:
            model_to_use = kwargs.pop("model", self._model)
            if model_to_use is None:
                # Or raise an error, or use a default defined in this class if appropriate
                raise ValueError("Model must be provided either at initialization or via kwargs.")

            # Initialize Gemini client with API key
            client = OpenAIClient(
                api_key=self._api_key,
                base_url=self._api_url,
                proxy="socks5://192.168.1.100:7890",
                timeout=60
            )
            _response = client.chat(
                system_prompt=SYSTEM_INSTRUCTIONS,
                images=[image],
                model=model_to_use,
                temperature=0,
                **kwargs,
            )
            if _result := client.get_full_response_info(_response):
                # area_list: List[ImageObjectArea] = [
                #     ImageObjectArea(**item)
                #     for item in extract_first_json_block(_result["content"])
                # ]
                # return area_list
                return extract_first_json_block(_result["content"])

            return None
        except Exception as e:
            logger.error(e)
            raise e
        finally:
            if client:
                client.close()


if __name__ == "__main__":
    import json



    challenger = SpatialBboxReasoner(
        gemini_api_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        gemini_api_key="sk-36ae94a95bfd4744860e348b2617b9fd",
        model="qwen2.5-vl-32b-instruct",
    )



    base_dir = "/home/bingo/PycharmProjects/tiny-tutorial/backend/app/images/captcha/tencent"
    # for file in os.listdir(base_dir):
    #     if file.endswith(".jpg"):
    #         image_path = os.path.join(base_dir, file)
    #         file_name = file.split(".")[1].split(".")[0].replace("请点击", "")
    #         result: List = challenger.invoke(
    #             image=image_path,
    #             prompt=file_name
    #         )
    #         with open(f"/home/bingo/PycharmProjects/tiny-tutorial/backend/app/images/captcha/tencent/{file.replace('.jpg', '')}.json",
    #                   "w") as f:
    #             f.write(json.dumps(result, indent=4, ensure_ascii=False))
    #         print(file, "==>", result)
    #         break

    image_path = os.path.join(base_dir, "148.请点击正方体上面的字母.jpg")
    file =  os.path.basename(image_path)
    file_name = file.split(".")[1].split(".")[0].replace("请点击", "")
    result: List = challenger.invoke(
        image=image_path,
        prompt=file_name
    )
    print(file, "==>", result)