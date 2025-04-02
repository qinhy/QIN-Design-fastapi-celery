import os
import json
import requests
from typing import Optional
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
                    api_key = self.model.param.api_key or os.environ.get('OPENAI_API_KEY')
                    if not api_key:
                        raise ValueError("OpenAI API key is missing. Provide via param.api_key or 'OPENAI_API_KEY' env var.")


                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {api_key}'
                    }

                    messages = []
                    if self.model.param.system_prompt:
                        messages.append({"role": "system", "content": self.model.param.system_prompt})
                    messages.append({"role": "user", "content": self.model.args.user_prompt})

                    payload = {
                        "model": self.model.param.model,
                        "messages": messages,
                        "temperature": self.model.param.temperature,
                        "max_tokens": self.model.param.max_tokens,
                        "top_p": self.model.param.top_p,
                        "stream": self.model.param.stream
                    }

                    self.log_and_send("Sending streaming request to OpenAI...")

                    response = requests.post(
                        url='https://api.openai.com/v1/chat/completions',
                        headers=headers,
                        data=json.dumps(payload),
                        stream=True
                    )

                    response.raise_for_status()

                    full_response = ""

                    for line in response.iter_lines():
                        if stop_flag.is_set():
                            return self.to_stop()

                        if line:
                            decoded = line.decode("utf-8").lstrip("data: ").strip()
                            if decoded == "[DONE]":
                                break
                            try:
                                chunk = json.loads(decoded)
                                delta = chunk['choices'][0]['delta'].get('content', '')
                                if delta:
                                    full_response += delta
                                    self.log_and_send(delta)
                            except json.JSONDecodeError:
                                self.log_and_send(f"Malformed chunk: {decoded}", ChatGPTService.Levels.WARNING)

                    self.model.ret.response = full_response
                    self.log_and_send("Streaming completed.")

                except Exception as e:
                    self.log_and_send(f"Error occurred: {str(e)}", ChatGPTService.Levels.ERROR)
                    self.model.ret.response = f"Error: {str(e)}"

            return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected. Streaming halted.", ChatGPTService.Levels.WARNING)
            self.model.ret.response = "[Stream stopped by user]"
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})