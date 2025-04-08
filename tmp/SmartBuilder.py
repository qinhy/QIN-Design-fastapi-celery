import os
import re
import json
import requests

class SmartBuilder:
    """
    A class for building and managing conversion functions between different
    ServiceOrientedArchitecture classes using LLM.
    """
    def __init__(self, model="gpt-4o-mini", api_key=None):
        """
        Initialize the SmartBuilder with configuration options.
        
        Parameters
        ----------
        model : str
            The LLM model to use for code generation
        api_key : str, optional
            OpenAI API key. If None, will try to get from environment variable
        """
        self.model = model
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("API key not found in environment variable 'OPENAI_API_KEY' and not provided")
    
    def build_conversion_prompt(
        self,
        source_class, 
        target_class,
        prompt_template: str = None
    ) -> tuple[str, str]:
        """
        Dynamically build a prompt that requests GPT to write a function
        converting `source_class`'s return to `target_class`'s args.

        Parameters
        ----------
        source_class : ServiceOrientedArchitecture
            The class with a .Model.ret schema to convert from.
        target_class : ServiceOrientedArchitecture
            The class with a .Model.args schema to convert to.
        prompt_template : str, optional
            Custom prompt template to use instead of the default one

        Returns
        -------
        tuple[str, str]
            A tuple of (prompt_text, generated_function_name).
        """
        if prompt_template is None:
            prompt_template = (
                "Please complete the following code and only provide the implementation of the ret to args converter function :\n\n"
                "```{from_class_name}.Model pydanctic schema\n"
                "{from_schema}\n"
                "```\n\n"
                "```{to_class_name}.Model pydanctic schema\n"
                "{to_schema}\n"
                "```\n\n"
                "```python\n"
                "def {from_class_name}{from_class_version}_ret_to_{to_class_name}{from_class_version}_args_convertor(ret,args):\n"
                "    # this function will convert {from_class_name}.ret into {to_class_name}.args\n"
                "    # ...\n"
                "    return args\n"
                "```"
            )

        from_class_name = source_class.__name__
        to_class_name = target_class.__name__
        from_class_version = source_class.Model.Version()
        to_class_version = target_class.Model.Version()

        prompt = prompt_template.format(
            from_class_name=from_class_name,
            from_schema=source_class.Model.Return.model_json_schema(),
            to_class_name=to_class_name,
            to_schema=target_class.Model.Args.model_json_schema(),
            from_class_version=from_class_version,
            to_class_version=to_class_version,
        )

        return prompt, f"{from_class_name}{from_class_version}_ret_to_{to_class_name}{from_class_version}_args_convertor"

    def get_func_from_code(self, code_string, function_name):
        """
        Extract a function from a code string.
        
        Parameters
        ----------
        code_string : str
            The code containing the function
        function_name : str
            The name of the function to extract
            
        Returns
        -------
        callable
            The extracted function
        """
        # Execute the extracted code in a new local namespace
        local_namespace = {}
        exec(code_string, globals(), local_namespace)

        # Return the requested function from that namespace
        func = local_namespace.get(function_name)
        if not func:
            raise ValueError(f"Function '{function_name}' not found in the code.")

        return func

    def get_code_from_gpt(self, prompt: str, function_name: str, model: str = None):
        """
        Given a prompt and a function name, this function calls the GPT API and
        extracts the code block containing the function. The code is then
        executed locally, and the specified function is returned as a callable.

        Parameters
        ----------
        prompt : str
            The prompt to send to GPT.
        function_name : str
            The name of the function to extract from GPT's response.
        model : str, optional
            The model to use for this specific request, overriding the default

        Returns
        -------
        tuple[str, callable]
            A tuple containing the extracted code string and the function object.

        Raises
        ------
        ValueError
            If the GPT response is invalid, or if the function is not found in the response.
        """
        model = model or self.model
        
        url = 'https://api.openai.com/v1/chat/completions'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        # Call the GPT API
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        message = response.json()['choices'][0]['message']['content']

        # Attempt to extract the code block
        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", message, re.DOTALL)
        if not code_blocks:
            raise ValueError('No code block found in GPT response.')
        code_string = code_blocks[0]

        return code_string, self.get_func_from_code(code_string, function_name)
    def build(self, in_class, out_class, model=None, prompt_template=None):
        """
        Build a conversion function between two ServiceOrientedArchitecture classes.
        
        Parameters
        ----------
        in_class : ServiceOrientedArchitecture
            The source class with return values to convert from
        out_class : ServiceOrientedArchitecture
            The target class with args to convert to
        model : str, optional
            The model to use for this specific build, overriding the default
        prompt_template : str, optional
            Custom prompt template to use for this specific build
            
        Returns
        -------
        callable
            The conversion function
        """
        # Build prompt
        prompt_text, function_name = self.build_conversion_prompt(
            in_class, 
            out_class,
            prompt_template
        )

        # Fetch code and function from GPT
        code_snippet, conversion_func = self.get_code_from_gpt(
            prompt_text, 
            function_name,
            model
        )

        return conversion_func
        
    def convert(self, in_class, in_model_instance,
                out_class, out_model_instance,
                model=None, prompt_template=None):

        # Build prompt
        prompt_text, function_name = self.build_conversion_prompt(in_class, out_class, prompt_template)

        # Fetch code and function from GPT
        code_snippet, conversion_func = self.get_code_from_gpt(prompt_text, function_name, model)

        in_ret_data = in_model_instance.ret.model_dump()
        out_args_data = out_model_instance.args.model_dump()

        # Execute the GPT-provided conversion function
        updated_args = conversion_func(in_ret_data, out_args_data)

        out_model_instance.args = out_model_instance.Args(**updated_args)
        return out_model_instance, code_snippet, conversion_func 



