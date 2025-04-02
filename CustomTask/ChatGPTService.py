import os
import json
import threading
import requests
from typing import Generator, Optional, Dict, Any
from pydantic import BaseModel, Field
from Task.Basic import ServiceOrientedArchitecture

class ChatGPTService(ServiceOrientedArchitecture):
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            api_key: Optional[str] = Field(None, description="OpenAI API key (optional if set in env)")
            model: str = Field("gpt-4o-mini", description="OpenAI model to use")
            temperature: float = Field(0.7, ge=0, le=2.0, description="Sampling temperature")
            max_tokens: int = Field(1024, ge=1, description="Maximum tokens to generate")
            top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
            stream: bool = Field(True, description="Whether to use streaming mode")
            system_prompt: Optional[str] = Field(None, description="Optional system prompt")

        class Args(BaseModel):
            user_prompt: str = Field(..., description="The user prompt to send to ChatGPT")

        class Return(BaseModel):
            response: str = Field("", description="The full model response")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {
                        "api_key": "OpenAI_API_key or in env",
                        "model": "gpt-4o-mini",
                        "system_prompt": "You are a helpful assistant.",
                    },
                    "args": {
                        "user_prompt": "What's a quick summary of the solar system?"
                    }
                },
                {
                    "param": {
                        "api_key": "OpenAI_API_key or in env",
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

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name="ChatGPTService")

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: ChatGPTService.Model = self.model
            self.logger = self.model.logger

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                try:
                    api_key: str = self._get_api_key()
                    headers: Dict[str, str] = self._build_headers(api_key)
                    payload: Dict[str, Any] = self._build_payload()

                    self.log_and_send("Sending streaming request to OpenAI...")
                    response: requests.Response = self._send_request(headers, payload)

                    full_response: str = ""
                    for delta in self._stream_response_chunks(response, stop_flag):
                        self.log_and_send(delta)
                        full_response += delta

                    self.model.ret.response = full_response
                    self.log_and_send("Streaming completed.")

                except Exception as e:
                    self._handle_error(e)

            return self.model


        def _get_api_key(self) -> str:
            api_key: Optional[str] = self.model.param.api_key or os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API key is missing. Provide via param.api_key or 'OPENAI_API_KEY' env var.")
            return api_key


        def _build_headers(self, api_key: str) -> Dict[str, str]:
            return {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }


        def _build_payload(self) -> Dict[str, Any]:
            messages: list[Dict[str, str]] = []
            if self.model.param.system_prompt:
                messages.append({"role": "system", "content": self.model.param.system_prompt})
            messages.append({"role": "user", "content": self.model.args.user_prompt})

            return {
                "model": self.model.param.model,
                "messages": messages,
                "temperature": self.model.param.temperature,
                "max_tokens": self.model.param.max_tokens,
                "top_p": self.model.param.top_p,
                "stream": self.model.param.stream
            }


        def _send_request(self, headers: Dict[str, str], payload: Dict[str, Any]) -> requests.Response:
            response = requests.post(
                url='https://api.openai.com/v1/chat/completions',
                headers=headers,
                data=json.dumps(payload),
                stream=True
            )
            response.raise_for_status()
            return response


        def _stream_response_chunks(self,
                                    response: requests.Response, 
                                    stop_flag: threading.Event) -> Generator[str, None, None]:
            for line in response.iter_lines():
                if stop_flag.is_set():
                    return

                if line:
                    decoded: str = self._decode_stream_line(line)
                    if decoded == "[DONE]":
                        break
                    try:
                        chunk: Dict[str, Any] = json.loads(decoded)
                        deltad: dict = chunk['choices'][0]['delta']
                        delta: str = deltad.get('content', '')
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        self.log_and_send(f"Malformed chunk: {decoded}", ChatGPTService.Levels.WARNING)


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
            self.send_data_to_task({level: message})




class MyChatGPTService(ChatGPTService):
    class Levels(ChatGPTService.Model.Levels):
        pass

    class Model(ChatGPTService.Model):

        class Param(ChatGPTService.Model.Param):
            my_input:str = "any thing"

        class Args(ChatGPTService.Model.Args):            
            my_input:str = "any thing"

        class Return(ChatGPTService.Model.Return):            
            my_ret:str = "any thing"

        class Logger(ChatGPTService.Model.Logger):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {
                        "my_input": "any thing"
                    },
                    "args": {                        
                        "my_input": "any thing"
                    }
                }
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name="ChatGPTService")

    class Action(ChatGPTService.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: MyChatGPTService.Model = self.model
            self.logger = self.model.logger

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                ## my preprocess
                # ...

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

                    self.log_and_send("Sending streaming request to OpenAI...")
                    response: requests.Response = self._send_request(headers, payload)

                    full_response: str = ""
                    for delta in self._stream_response_chunks(response, stop_flag):
                        self.log_and_send(delta)
                        full_response += delta

                    self.model.ret.response = full_response
                    self.log_and_send("Streaming completed.")

                except Exception as e:
                    self._handle_error(e)

                ## my postprocess
                # ...
            return self.model



