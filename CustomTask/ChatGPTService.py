import os
import json
import threading
import requests
from typing import Generator, Optional, Dict, Any
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union
import base64
import mimetypes
from pathlib import Path

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import FileInputHelper
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import FileInputHelper


class PromptBuilder:
    def __init__(self, system_prompt: Optional[str] = None):
        self.messages: List[Dict[str, Union[str, Dict]]] = []
        if system_prompt:
            self.add_system(system_prompt)

    def add_system(self, content: str):
        self.messages.append({"role": "system", "content": content})
        return self

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})
        return self

    def add_assistant(self, content: str):
        self.messages.append({"role": "assistant", "content": content})
        return self

    def add_image(self, image_path: Union[str, Path], role: str = "user", detail: str = "auto"):
        """
        Adds an image input for multimodal models like GPT-4o. `detail` can be "auto", "low", or "high".
        """
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type or not mime_type.startswith("image/"):
            raise ValueError(f"Invalid image type for: {image_path}")

        with FileInputHelper.open(image_path, "rb") as img_file:
            b64_image = base64.b64encode(img_file.read()).decode("utf-8")

        self.messages.append({
            "role": role,
            "content": [
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{b64_image}",
                    "detail": detail
                }}
            ]
        })
        return self

    def add_file_note(self, note: str, role: str = "user"):
        """
        Add a note referring to an uploaded file (for non-image files)
        """
        self.messages.append({"role": role, "content": note})
        return self

    def build(self) -> List[Dict[str, Union[str, Dict]]]:
        return self.messages


class ChatGPTService(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Provides an interface to interact with ChatGPT and other OpenAI models.
Supports text generation, completion, and multimodal capabilities.
Allows customization of model parameters and handles API communication.
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            api_key: Optional[str] = Field(None, description="OpenAI API key (optional if set in env)")
            model: str = Field("gpt-4o-mini", description="OpenAI model to use")
            temperature: float = Field(0.7, ge=0, le=2.0, description="Sampling temperature")
            max_tokens: int = Field(1024, ge=1, description="Maximum tokens to generate")
            top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
            stream: bool = Field(False, description="Whether to use streaming mode")
            system_prompt: Optional[str] = Field(None, description="Optional system prompt")
            base_url: str = Field("https://api.openai.com/v1/chat/completions", description="OpenAI API endpoint")


        class Args(BaseModel):
            user_prompt: str = Field("Hi", description="The user prompt to send to ChatGPT")
            messages: List[Dict[str, Union[str, Dict]]] = Field([], description="The messages to send to ChatGPT")

        class Return(BaseModel):
            response: str = Field("", description="The full model response")

        
        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {
                        "api_key": None,#"OpenAI_API_key or in env",
                        "model": "gpt-4o-mini",
                        "system_prompt": "You are a helpful assistant.",
                    },
                    "args": {
                        "user_prompt": "What's a quick summary of the solar system?"
                    }
                },
                {
                    "param": {
                        "api_key": None,#"OpenAI_API_key or in env",
                        "model": "gpt-4o-mini",
                        "system_prompt": "You are a helpful assistant.",
                        "temperature": 0.5,
                        "max_tokens": 100,
                        "top_p": 1.0
                    },
                    "args": {
                        "user_prompt": "What's a quick summary of the solar system?"
                    }
                }
            ]

        version:Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: ChatGPTService.Model = self.model
            self.logger = self.model.logger

        def __call__(self, *args, **kwargs) -> Any:
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                try:
                    param = self.model.param
                    args_obj = self.model.args

                    api_key: str = self._get_api_key(param.api_key)
                    headers: Dict[str, str] = self._build_headers(api_key)
                    payload: Dict[str, Any] = self._build_payload(
                        model=param.model,
                        system_prompt=param.system_prompt,
                        user_prompt=args_obj.user_prompt,
                        temperature=param.temperature,
                        max_tokens=param.max_tokens,
                        top_p=param.top_p,
                        stream=param.stream
                    )

                    self.log_and_send("Sending request to OpenAI...")
                    response: requests.Response = self._send_request(headers, payload)

                    if param.stream:
                        full_response: str = ""
                        for delta in self._stream_response_chunks(response, stop_flag):
                            self.log_and_send(delta)
                            full_response += delta
                    else:
                        full_response = self._handle_non_stream_response(response)

                    self.model.ret.response = full_response
                    self.log_and_send("Response completed.")

                except Exception as e:
                    self._handle_error(e)

            return self.model


        def _get_api_key(self, param_key: Optional[str], env_key: Optional[str]='OPENAI_API_KEY') -> str:
            api_key: Optional[str] = param_key or os.environ.get(env_key)
            if not api_key:
                raise ValueError(f"API key is missing. Provide via param.api_key or '{env_key}' env var.")
            return api_key


        def _build_headers(self, api_key: str) -> Dict[str, str]:
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }


        def _build_payload(
            self,
            model: str,
            system_prompt: Optional[str],
            user_prompt: str,
            temperature: float,
            max_tokens: int,
            top_p: float,
            stream: bool
        ) -> Dict[str, Any]:
            if self.model.args.messages:
                messages = self.model.args.messages
            else:
                messages = []

            # check if messages has system prompt
            has_system_prompt = any(msg.get("role") == "system" for msg in messages)
            
            # Only add system prompt if it doesn't already exist in messages
            if system_prompt and not has_system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})

            messages.append({"role": "user", "content": user_prompt})

            return {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p,
                "stream": stream
            }


        def _send_request(self, headers: Dict[str, str], payload: Dict[str, Any]) -> requests.Response:
            response = requests.post(
                url=self.model.param.base_url,
                headers=headers,
                data=json.dumps(payload),
                stream=True
            )
            response.raise_for_status()
            return response


        def _stream_response_chunks(self, response: requests.Response, stop_flag: threading.Event) -> Generator[str, None, None]:
            for line in response.iter_lines():
                if stop_flag.is_set():
                    return

                if line:
                    decoded: str = self._decode_stream_line(line)
                    if decoded == "[DONE]":
                        break
                    try:
                        chunk: Dict[str, Any] = json.loads(decoded)
                        delta: str = chunk['choices'][0]['delta'].get('content', '')
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        self.log_and_send(f"Malformed chunk: {decoded}", ChatGPTService.Levels.WARNING)

        def _handle_non_stream_response(self, response: requests.Response) -> str:
            try:
                data: Dict[str, Any] = response.json()
                return data['choices'][0]['message']['content']
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                raise RuntimeError(f"Failed to parse non-stream response: {str(e)}")

        def _decode_stream_line(self, line: bytes) -> str:
            decoded_line: str = line.decode("utf-8").strip()
            if decoded_line.startswith("data:"):
                return decoded_line[len("data:"):].strip()
            return decoded_line


        def _handle_error(self, e: Exception) -> None:
            error_message: str = f"Error occurred: {str(e)}"
            self.log_and_send(error_message, ChatGPTService.Levels.ERROR)
            self.model.ret.response = f"Error: {str(e)}"

        def to_stop(self):
            self.log_and_send("Stop flag detected. Streaming halted.", ChatGPTService.Levels.WARNING)
            self.model.ret.response = "[Stream stopped by user]"
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            # self.send_data_to_task({level: message})

class DeepseekService(ChatGPTService):
    @classmethod
    def description(cls):
        return """
Provides an interface to interact with deepseek models.
"""
    class Levels(ChatGPTService.Levels):
        pass

    class Model(ChatGPTService.Model):
        class Param(ChatGPTService.Model.Param):
            model: str = Field("deepseek-reasoner", description="Deepseek model to use")
            base_url: str = Field("https://api.deepseek.com/v1/chat/completions", description="Deepseek API endpoint")

        class Args(ChatGPTService.Model.Args):
            pass

        class Return(BaseModel):
            response: str = Field("", description="The assistant's final response")
            reasoning: Optional[str] = Field(None, description="The model's internal reasoning process")

        class Logger(ChatGPTService.Model.Logger):
            pass
        class Version(ChatGPTService.Model.Version):
            pass

        version:Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ChatGPTService.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: DeepseekService.Model = self.model

        def _get_api_key(self, param_key: Optional[str], env_key: Optional[str]='DEEPSEEK_API_KEY') -> str:
            return super()._get_api_key(param_key, env_key)
        
        def __call__(self, *args, **kwargs) -> Any:
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                try:
                    param = self.model.param
                    args_obj = self.model.args

                    api_key: str = self._get_api_key(param.api_key)
                    headers: Dict[str, str] = self._build_headers(api_key)
                    payload: Dict[str, Any] = self._build_payload(
                        model=param.model,
                        system_prompt=param.system_prompt,
                        user_prompt=args_obj.user_prompt,
                        temperature=param.temperature,
                        max_tokens=param.max_tokens,
                        top_p=param.top_p,
                        stream=param.stream
                    )

                    self.log_and_send("Sending request to Deepseek...")
                    response: requests.Response = self._send_request(headers, payload)

                    if param.stream:
                        content, reasoning = self._stream_response_chunks(response, stop_flag)
                    else:
                        content = self._handle_non_stream_response(response)
                        reasoning = self.model.ret.reasoning or ""

                    self.model.ret.response = content
                    self.model.ret.reasoning = reasoning

                    if reasoning:
                        self.log_and_send("Full reasoning:\n" + reasoning)
                    self.log_and_send("Response completed.")

                except Exception as e:
                    self._handle_error(e)

            return self.model

        def _stream_response_chunks(self, response: requests.Response, stop_flag: threading.Event):
            content = ""
            reasoning = ""

            for line in response.iter_lines():
                if stop_flag.is_set():
                    break

                if line:
                    decoded = self._decode_stream_line(line)
                    if decoded == "[DONE]":
                        break

                    try:
                        chunk = json.loads(decoded)
                        delta = chunk['choices'][0]['delta']

                        reasoning_delta = delta.get('reasoning_content', '')
                        content_delta = delta.get('content', '')

                        if reasoning_delta:
                            self.log_and_send(f"[Reasoning] {reasoning_delta}")
                            reasoning += reasoning_delta

                        if content_delta:
                            self.log_and_send(content_delta)
                            content += content_delta

                    except json.JSONDecodeError:
                        self.log_and_send(f"Malformed chunk: {decoded}", DeepseekService.Levels.WARNING)

            return content, reasoning

        def _handle_non_stream_response(self, response: requests.Response) -> str:
            try:
                data: Dict[str, Any] = response.json()
                message = data['choices'][0]['message']
                content = message.get('content', '')
                reasoning = message.get('reasoning_content')
                self.model.ret.reasoning = reasoning
                return content
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                raise RuntimeError(f"Failed to parse non-stream response: {str(e)}")

                
def test_chatgpt_service():
    """Simple test function for ChatGPTService"""
    # Create a service instance
    model = ChatGPTService.Model()
    
    # Configure parameters
    model.param.model = "gpt-4o-mini"  # Use a smaller model for testing
    model.param.api_key = os.environ.get('OPENAI_API_KEY')
    model.param.max_tokens = 50  # Limit response size
    model.param.stream = False  # Disable streaming for simpler testing
    
    # Set the user prompt
    model.args.user_prompt = "Hi what is your name?"
    
    # Run the service
    try:
        result = ChatGPTService.Action(model,None)()
        print("\nTest Result:")
        print(f"Prompt: {model.args.user_prompt}")
        print(f"Response: {result.ret.response}")
        print("Test end!")
        return True
    except Exception as e:
        print(f"Test failed with error: {str(e)}")
        return False

def test_chatgpt_service_with_image():
    """Test function using PromptBuilder with image input"""
    from pathlib import Path

    image_path = Path("./tmp/Lenna_(test_image).png")
    if not image_path.exists():
        print(f"Test image not found at {image_path}")
        return False

    # Build prompt with image
    prompt = PromptBuilder(system_prompt="You are a visual assistant.")
    prompt.add_user("What is in this image?")
    prompt.add_image(image_path)

    # Create service model
    model = ChatGPTService.Model()
    model.param.model = "gpt-4.1-nano"  # Make sure to use a vision-capable model
    model.param.api_key = os.environ.get('OPENAI_API_KEY')
    model.param.stream = False
    model.param.max_tokens = 100

    # Set messages from PromptBuilder
    model.args.messages = prompt.build()
    model.args.user_prompt = ""  # No additional prompt needed

    # Run the service
    try:
        result = ChatGPTService.Action(model, None)()
        print("\nTest with Image Result:")
        print(f"Response: {result.ret.response}")
        print("Image test end!")
        return True
    except Exception as e:
        print(f"Image test failed with error: {str(e)}")
        return False

def test_deepseek_service():
    """Simple test function for DeepseekService"""
    import os

    # Create a service instance
    model = DeepseekService.Model()

    # Configure parameters
    model.param.model = "deepseek-reasoner"
    model.param.api_key = os.environ.get('DEEPSEEK_API_KEY')  # Make sure this is set
    model.param.max_tokens = 50
    model.param.stream = True
    model.param.system_prompt = "You are a logical assistant."

    # Set the user prompt
    model.args.user_prompt = "Which is greater, 3.14 or 2.718?"

    # Run the service
    try:
        result = DeepseekService.Action(model, None)()
        print("\nTest Result:")
        print(f"Prompt: {model.args.user_prompt}")
        print(f"Reasoning: {result.ret.reasoning}")
        print(f"Response: {result.ret.response}")
        print("Test end!")
        return True
    except Exception as e:
        print(f"Test failed with error: {str(e)}")
        return False


if __name__ == "__main__":
    # Run the test when the script is executed directly
    test_chatgpt_service()
    # test_chatgpt_service_with_image()
    test_deepseek_service()
