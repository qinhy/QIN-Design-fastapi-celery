from typing import Optional
from pydantic import BaseModel, Field
import os
import json
import requests
import re

try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class SmartModelConverter(ServiceOrientedArchitecture):
    """
    A class for building and managing conversion functions between different
    ServiceOrientedArchitecture classes using LLM.
    """

    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            model: str = Field("gpt-4o-mini", description="The model to use for conversion.")
            api_key: Optional[str] = Field(None, description="API key for authentication, if required.")

        class Args(BaseModel):
            source_class_name: str = Field(None, description="The source class name for conversion.")
            target_class_name: str = Field(None, description="The target class name for conversion.")
            prompt_template: str = Field(
                (
                    "Please complete the following code and only provide the implementation "
                    "of the ret to args converter function:\n\n"
                    "```{from_class_name}.Model pydanctic schema\n"
                    "{from_schema}\n"
                    "```\n\n"
                    "```{to_class_name}.Model pydanctic schema\n"
                    "{to_schema}\n"
                    "```\n\n"
                    "```python\n"
                    "def {from_class_name}{from_class_version}_ret_to_{to_class_name}{from_class_version}_args_convertor"
                    "(ret, args):\n"
                    "    # this function will convert {from_class_name}.ret into {to_class_name}.args\n"
                    "    # ...\n"
                    "    return args\n"
                    "```"
                ),
                description="Template for generating the conversion function prompt."
            )
        class Return(BaseModel):
            function_name: str = Field("", description="The name of the conversion function.")
            code_snippet: str = Field("", description="The code snippet generated for the conversion function.")

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        version:Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        ACTION_REGISTRY:dict[str, ServiceOrientedArchitecture] = {}

        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: SmartModelConverter.Model = self.model
            self.Levels = SmartModelConverter.Model.Logger.Levels

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()
                
                self.log_and_send("Starting SmartModelConverter execution", self.Levels.INFO)
                
                self.model.param.api_key = self.model.param.api_key or os.environ.get('OPENAI_API_KEY')
                if not self.model.param.api_key:
                    self.log_and_send("API key not found in environment or parameters", self.Levels.ERROR)
                    raise ValueError("API key not found in environment variable 'OPENAI_API_KEY' and not provided")

                self.log_and_send(f"Building conversion prompt for {self.model.args.source_class_name} to {self.model.args.target_class_name}", self.Levels.INFO)
                source_class = self.ACTION_REGISTRY[self.model.args.source_class_name]
                target_class = self.ACTION_REGISTRY[self.model.args.target_class_name]
                prompt_text, function_name = self.build_conversion_prompt(
                    source_class,
                    target_class,
                    self.model.args.prompt_template
                )
                self.log_and_send(f"Generated function name: {function_name}", self.Levels.DEBUG)

                self.log_and_send(f"Requesting code generation using model: {self.model.param.model}", self.Levels.INFO)
                code_snippet, conversion_func = self.get_code_from_gpt(
                    prompt_text,
                    function_name,
                    self.model.param.model
                )
                self.log_and_send("Successfully generated conversion function", self.Levels.INFO)
                self.model.ret.function_name = function_name
                self.model.ret.code_snippet = code_snippet

                self.log_and_send("SmartModelConverter execution completed successfully", self.Levels.INFO)
                return self.model

        def build_conversion_prompt(self, source_class, target_class, prompt_template: str = None) -> tuple[str, str]:
            if prompt_template is None:
                prompt_template = self.model.args.prompt_template

            from_class_name = source_class.__name__
            to_class_name = target_class.__name__
            from_class_version = source_class.Model.Version()
            to_class_version = target_class.Model.Version()

            self.log_and_send(f"Building prompt for {from_class_name}(v{from_class_version}) to {to_class_name}(v{to_class_version})", self.Levels.DEBUG)
            
            prompt = prompt_template.format(
                from_class_name=from_class_name,
                from_schema=source_class.Model.Return.model_json_schema(),
                to_class_name=to_class_name,
                to_schema=target_class.Model.Args.model_json_schema(),
                from_class_version=from_class_version,
                to_class_version=to_class_version,
            )

            function_name = self.get_function_name(source_class, target_class)
            self.log_and_send(f"Prompt built successfully with {len(prompt)} characters", self.Levels.DEBUG)
            return prompt, function_name

        def get_function_name(self, source_class, target_class):
            from_class_name = source_class.__name__
            to_class_name = target_class.__name__
            from_class_version = source_class.Model.Version()
            to_class_version = target_class.Model.Version()
            function_name = f"{from_class_name}{from_class_version}_ret_to_{to_class_name}{to_class_version}_args_convertor"
            self.log_and_send(f"Generated function name: {function_name}", self.Levels.DEBUG)
            return function_name

        def get_func_from_code(self, code_string, function_name):
            self.log_and_send(f"Extracting function '{function_name}' from code", self.Levels.DEBUG)
            local_namespace = {}
            try:
                exec(code_string, globals(), local_namespace)
                func = local_namespace.get(function_name)
                if not func:
                    self.log_and_send(f"Function '{function_name}' not found in the code", self.Levels.ERROR)
                    raise ValueError(f"Function '{function_name}' not found in the code.")
                self.log_and_send(f"Successfully extracted function '{function_name}'", self.Levels.DEBUG)
                return func
            except Exception as e:
                self.log_and_send(f"Error executing code: {str(e)}", self.Levels.ERROR)
                raise

        def get_code_from_gpt(self, prompt: str, function_name: str, model: str = None):
            model = model or self.model.param.model
            url = 'https://api.openai.com/v1/chat/completions'
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.model.param.api_key}'
            }
            data = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }

            self.log_and_send(f"Sending request to OpenAI API using model: {model}", self.Levels.INFO)
            try:
                response = requests.post(url, headers=headers, data=json.dumps(data))
                response.raise_for_status()
                self.log_and_send("Received successful response from OpenAI API", self.Levels.INFO)
                
                message = response.json()['choices'][0]['message']['content']
                self.log_and_send(f"Response content length: {len(message)} characters", self.Levels.DEBUG)
                
                code_blocks = re.findall(r"```(?:python)?\n(.*?)```", message, re.DOTALL)
                if not code_blocks:
                    self.log_and_send("No code block found in GPT response", self.Levels.ERROR)
                    raise ValueError('No code block found in GPT response.')
                
                code_string = code_blocks[0]
                self.log_and_send(f"Extracted code block of {len(code_string)} characters", self.Levels.DEBUG)
                
                return code_string, self.get_func_from_code(code_string, function_name)
            except requests.exceptions.RequestException as e:
                self.log_and_send(f"API request error: {str(e)}", self.Levels.ERROR)
                raise

        def to_stop(self):
            self.log_and_send("Stop flag detected, returning 0.", self.Levels.WARNING)
            self.model.ret = None
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})

# Simple test for SmartModelConverter
if __name__ == "__main__":
            
    from Fibonacci import Fibonacci
    from PrimeNumberChecker import PrimeNumberChecker
    # Set up the registry
    SmartModelConverter.Action.ACTION_REGISTRY = {
        'Fibonacci': Fibonacci,
        'PrimeNumberChecker': PrimeNumberChecker
    }
    
    # Create model instance
    model = SmartModelConverter.Model()
    model.args.source_class_name = "Fibonacci"
    model.args.target_class_name = "PrimeNumberChecker"
    model.param.api_key = os.environ.get('OPENAI_API_KEY')
    
    model = SmartModelConverter.Action(model, None)()
    
    
    print(f"Generated code: {model.ret.function_name}\n{model.ret.code_snippet}")
    print("Test completed successfully")
