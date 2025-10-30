import os
import json
import threading
import requests
from typing import Generator, Literal, Optional, Dict, Any
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


class ResponsesInputBuilder:
    """
    Builder for OpenAI Responses API 'input' payloads.
    Produces a list of turn objects with {role, content}.
    Each 'content' is a list of parts: input_text / input_image, per docs.
    """
    def __init__(self, system_prompt: Optional[str] = None):
        # For Responses API, 'system' is usually passed via 'instructions'
        # but we keep it here for convenience; the service will move it.
        self._system_prompt: Optional[str] = system_prompt
        self._input: List[Dict[str, Any]] = []

    # --- text helpers ---

    def add_user(self, content: str) -> "ResponsesInputBuilder":
        self._input.append({
            "role": "user",
            "content": [{"type": "input_text", "text": content}]
        })
        return self

    def add_assistant(self, content: str) -> "ResponsesInputBuilder":
        self._input.append({
            "role": "assistant",
            "content": [{"type": "output_text", "text": content}]  # prior assistant turn
        })
        return self

    # --- image helpers ---

    def add_image(
        self,
        image_path: Union[str, Path],
        role: str = "user",
        detail: Optional[str] = None,
    ) -> "ResponsesInputBuilder":
        """
        Adds an image input part for multimodal models (e.g., GPT-4o/5).
        Uses 'input_image' type with a data: URL (base64) or remote URL.
        The 'detail' hint is optional and may be ignored by some models.
        """
        mime_type, _ = mimetypes.guess_type(str(image_path))

        if isinstance(image_path, (str, Path)) and (str(image_path).startswith("http://") or str(image_path).startswith("https://")):
            # Remote URL
            image_part: Dict[str, Any] = {"type": "input_image", "image_url": str(image_path)}
        else:
            if not mime_type or not mime_type.startswith("image/"):
                raise ValueError(f"Invalid image type for: {image_path}")
            # NOTE: FileInputHelper assumed present in your codebase (unchanged)
            with FileInputHelper.open(image_path, "rb") as img_file:
                b64_image = base64.b64encode(img_file.read()).decode("utf-8")
            image_part = {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{b64_image}"
            }

        if detail:
            image_part["detail"] = detail  # e.g., "low" | "high"

        self._input.append({
            "role": role,
            "content": [image_part]
        })
        return self

    def add_file_note(self, note: str, role: str = "user") -> "ResponsesInputBuilder":
        """
        Adds a textual note (e.g., referencing an uploaded non-image file).
        """
        self._input.append({
            "role": role,
            "content": [{"type": "input_text", "text": note}]
        })
        return self

    def build(self) -> Dict[str, Any]:
        """
        Returns a dict with:
          - 'instructions' (if a system prompt was provided)
          - 'input' (list of role/content messages)
        The service will merge this with its own 'user_prompt' if supplied.
        """
        payload: Dict[str, Any] = {"input": self._input}
        if self._system_prompt:
            payload["instructions"] = self._system_prompt
        return payload

class ChatGPTService(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Provides an interface to interact with OpenAI models via the Responses API.
Supports text + multimodal input, streaming, and customization of model parameters.
"""

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Parameter(BaseModel):
            class ReasoningParameter(BaseModel):
                """Controls the model's chain-of-thought *style* (not the content you receive)."""
                effort: Literal["low", "medium", "high"] = Field(
                    "low",description="How much reasoning effort to spend (latency/$$ trade-off).")
                summary: Literal["auto", "concise", "detailed"] = Field("auto",
                    description="How much reasoning *summary* to include in the response.")
                
            api_key: Optional[str] = Field(None, description="OpenAI API key (optional if set in env)")
            model: str = Field("gpt-5-nano", description="OpenAI model to use")
            temperature: float = Field(1.0, ge=0, le=2.0, description="Sampling temperature")
            max_output_tokens: int = Field(1024, ge=1, description="(Compat) Maximum tokens to generate; mapped to max_output_tokens")
            top_p: float = Field(1.0, ge=0.0, le=1.0, description="Nucleus sampling parameter")
            stream: bool = Field(False, description="Whether to use streaming mode")
            system_prompt: Optional[str] = Field(None, description="Optional system prompt (sent as 'instructions')")
            base_url: str = Field("https://api.openai.com/v1/responses", description="OpenAI Responses API endpoint")
            previous_response_id: Optional[str] = Field(None, description="Chain context across turns (optional).")
            reasoning: Optional[ReasoningParameter] = Field(
                None,
                description="Optional reasoning controls for the Responses API."
            )

        class Args(BaseModel):
            class SimpleTextMsg(BaseModel):
                role: str = Field("user", description="The role of the msg")
                content: str = Field("hi", description="The content of the msg")

            history_messages: List[SimpleTextMsg] = Field([],
                    description="(Compat) Chat-style messages; converted to Responses API 'input'."
            )
            user_prompt: str = Field("Hi", description="The user prompt to send to the model")

        class Return(BaseModel):
            response: str = Field("", description="The full model response text")
            response_id: Optional[str] = Field(None, description="The response.id from the API (for chaining).")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
                {
                    "param": {
                        "api_key": None,
                        "model": "gpt-4o-mini",
                        "system_prompt": "You are a helpful assistant.",
                    },
                    "args": {
                        "user_prompt": "What's a quick summary of the solar system?"
                    }
                },
                {
                "param": {
                    "api_key": None,
                    "max_output_tokens":1024,
                    "reasoning": {
                        "effort": "low",
                        "summary": "auto"
                    },
                    "model": "gpt-5-nano"
                },
                "args": {
                    "user_prompt": "JSON format of Tokyo info"
                }
                }
            ]

        version: Version = Version()
        para: Parameter = Parameter()
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
                    param = self.model.para
                    args_obj = self.model.args

                    api_key: str = self._get_api_key(param.api_key)
                    headers: Dict[str, str] = self._build_headers(api_key)
                    payload: Dict[str, Any] = self._build_payload(
                        model=param.model,
                        system_prompt=param.system_prompt,
                        user_prompt=args_obj.user_prompt,
                        temperature=param.temperature,
                        max_output_tokens=param.max_output_tokens,  # map compat -> responses field
                        top_p=param.top_p,
                        stream=param.stream,
                        previous_response_id=param.previous_response_id
                    )

                    self.log_and_send("Sending request to OpenAI (Responses API)...")
                    response: requests.Response = self._send_request(headers, payload)

                    if param.stream:
                        full_text: str = ""
                        response_id: Optional[str] = None
                        for text_delta, evt in self._stream_response_events(response, stop_flag):
                            if text_delta:
                                self.log_and_send(text_delta)
                                full_text += text_delta
                            # capture the final response id on completion
                            if evt and evt.get("type") == "response.completed":
                                response_id = (evt.get("response") or {}).get("id")
                        self.model.ret.response = full_text
                        self.model.ret.response_id = response_id
                    else:
                        full_text,reasoning, response_id = self._handle_non_stream_response(response)
                        self.model.ret.response = full_text
                        self.model.ret.response_id = response_id

                    self.log_and_send("Response completed.")

                except Exception as e:
                    self._handle_error(e)

            return self.model

        # --- utils ---

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

        def _convert_legacy_messages_to_input(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            """
            Converts Chat Completions-style messages to Responses 'input'.
            - If content is str -> wraps in [{"type":"input_text","text":...}] for user/developer text.
            - If content is list with image_url type -> converts to 'input_image'.
            - Assistant messages are included as prior context with 'output_text' type.
            """
            input_list: List[Dict[str, Any]] = []

            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")

                # Normalize to content parts
                parts: List[Dict[str, Any]] = []
                if isinstance(content, str):
                    # Treat as text input
                    if role == "assistant":
                        parts = [{"type": "output_text", "text": content}]
                    else:
                        parts = [{"type": "input_text", "text": content}]
                elif isinstance(content, list):
                    # Convert any legacy image_url parts to input_image
                    for p in content:
                        if p.get("type") == "image_url":
                            img = p.get("image_url") or {}
                            url = img.get("url")
                            detail = img.get("detail")
                            ipart: Dict[str, Any] = {"type": "input_image", "image_url": url}
                            if detail:
                                ipart["detail"] = detail
                            parts.append(ipart)
                        elif p.get("type") in ("input_text", "output_text", "input_image"):
                            parts.append(p)  # already responses-style
                        else:
                            # Fallback: treat unknown as text
                            txt = p.get("text") or json.dumps(p)
                            kind = "output_text" if role == "assistant" else "input_text"
                            parts.append({"type": kind, "text": txt})
                else:
                    # Unexpected -> stringify
                    parts = [{"type": "input_text", "text": json.dumps(content)}]

                input_list.append({"role": role, "content": parts})

            return input_list

        def _build_payload(
            self,
            model: str,
            system_prompt: Optional[str],
            user_prompt: str,
            temperature: float,
            max_output_tokens: int,
            top_p: float,
            stream: bool,
            previous_response_id: Optional[str]
        ) -> Dict[str, Any]:

            # Start with any pre-supplied messages (compat path)
            if self.model.args.history_messages:
                input_list = self._convert_legacy_messages_to_input(self.model.args.history_messages)
            else:
                input_list = []

            # Append the new user prompt
            input_list.append({
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}]
            })

            payload: Dict[str, Any] = {
                "model": model,
                "input": input_list,
                "temperature": temperature,
                "top_p": top_p,
                "max_output_tokens": max_output_tokens,
                "stream": stream,
            }
            if self.model.para.reasoning:
                payload["reasoning"] = self.model.para.reasoning.model_dump()

            # system prompt becomes 'instructions' for Responses API
            if system_prompt:
                payload["instructions"] = system_prompt

            if previous_response_id:
                payload["previous_response_id"] = previous_response_id  # chain context

            return payload

        def _send_request(self, headers: Dict[str, str], payload: Dict[str, Any]) -> requests.Response:
            response = requests.post(
                url=self.model.para.base_url,
                headers=headers,
                data=json.dumps(payload),
                stream=True  # keep stream open even if not streaming; ok for .json() too
            )
            response.raise_for_status()
            return response

        # --- streaming ---

        def _stream_response_events(
            self,
            response: requests.Response,
            stop_flag: threading.Event
        ) -> Generator[tuple[str, Optional[Dict[str, Any]]], None, None]:
            """
            Yields (text_delta, raw_event_dict_or_none) while streaming.
            Handles Responses API event types, e.g.:
              - response.output_text.delta (accumulate)
              - response.completed (stop)
              - response.error (raise/log)
            See: official event naming in docs / Agents SDK examples.
            """
            for raw in response.iter_lines(decode_unicode=True):
                if stop_flag.is_set():
                    return
                if not raw:
                    continue

                line = raw.strip()
                if not line:
                    continue

                # SSE lines may include "event:" and "data:"; we care about JSON in data
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()
                elif line.startswith("{"):
                    data_str = line  # plain JSONL
                else:
                    # ignore non-data lines (e.g., "event: ...")
                    continue

                if data_str == "[DONE]":
                    break
                self.log_and_send(f"Stream chunk: {data_str}", ChatGPTService.Levels.INFO)
                try:
                    evt = json.loads(data_str)
                except json.JSONDecodeError:
                    self.log_and_send(f"Malformed stream chunk: {line}", ChatGPTService.Levels.WARNING)
                    continue

                evt_type = evt.get("type", "")
                if evt_type == "response.output_text.delta":
                    delta = evt.get("delta", "")
                    if delta:
                        yield delta, evt
                elif evt_type == "response.completed":
                    # final event contains response metadata including id
                    yield "", evt
                    break
                elif evt_type == "response.error":
                    err = evt.get("error", {})
                    raise RuntimeError(f"API streaming error: {err}")
                else:
                    # Other event types: ignore or log (e.g., tool events)
                    pass

        # --- non-stream ---

        def _handle_non_stream_response(self, response: requests.Response) -> tuple[str, Optional[str]]:
            """
            Parses non-stream Responses API output.
            Returns (output_text, response_id).
            """
            try:
                data: Dict[str, Any] = response.json()
                full_text: str = ""
                reasoning: list = []
                for output in data.get("output", []):
                    t = output.get("type")
                    if t == 'reasoning':
                        reasoning = output["summary"]
                    elif t == 'message':
                        for c in output["content"]:
                            if c.get("type") == "output_text":
                                message = c.get("text", "")
                                full_text += message
                    elif t == 'tool_call':
                        tool_name = output["tool_name"]
                        tool_args = output["tool_args"]
                        self.log_and_send(f"Tool call: {tool_name} with args {tool_args}")

                resp_id: Optional[str] = data.get("id")
                return full_text, reasoning, resp_id
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                raise RuntimeError(f"Failed to parse non-stream response: {str(e)}")

        # --- misc ---

        def _handle_error(self, e: Exception) -> None:
            error_message: str = f"Error occurred: {str(e)}"
            self.log_and_send(error_message, ChatGPTService.Levels.ERROR)
            # Also propagate into return container
            if self.model.ret is None:
                self.model.ret = ChatGPTService.Model.Return()
            self.model.ret.response = f"Error: {str(e)}"

        def to_stop(self):
            self.log_and_send("Stop flag detected. Streaming halted.", ChatGPTService.Levels.WARNING)
            if self.model.ret is None:
                self.model.ret = ChatGPTService.Model.Return()
            self.model.ret.response = "[Stream stopped by user]"
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            # self.send_data_to_task({level: message})
  
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
    
class DeepseekService(ChatGPTService):
    @classmethod
    def description(cls):
        return """
Provides an interface to interact with deepseek models.
"""
    class Levels(ChatGPTService.Levels):
        pass

    class Model(ChatGPTService.Model):
        class Parameter(ChatGPTService.Model.Parameter):
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
        para: Parameter = Parameter()
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
                    param = self.model.para
                    args_obj = self.model.args

                    api_key: str = self._get_api_key(param.api_key)
                    headers: Dict[str, str] = self._build_headers(api_key)
                    payload: Dict[str, Any] = self._build_payload(
                        model=param.model,
                        system_prompt=param.system_prompt,
                        user_prompt=args_obj.user_prompt,
                        temperature=param.temperature,
                        max_output_tokens=param.max_output_tokens,
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
    model.para.model = "gpt-5-nano"  # Use a smaller model for testing
    model.para.api_key = os.environ.get('OPENAI_API_KEY')
    model.para.max_output_tokens = 256  # Limit response size
    model.para.stream = False  # Disable streaming for simpler testing
    
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
    model.para.model = "gpt-4.1-nano"  # Make sure to use a vision-capable model
    model.para.api_key = os.environ.get('OPENAI_API_KEY')
    model.para.stream = False
    model.para.max_output_tokens = 100

    # Set messages from PromptBuilder
    model.args.history_messages = prompt.build()
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
    model.para.model = "deepseek-reasoner"
    model.para.api_key = os.environ.get('DEEPSEEK_API_KEY')  # Make sure this is set
    model.para.max_output_tokens = 50
    model.para.stream = True
    model.para.system_prompt = "You are a logical assistant."

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
    # test_deepseek_service()
