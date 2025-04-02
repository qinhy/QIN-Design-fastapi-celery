import os
import re
import json
import requests
from typing import Literal, Optional
from pydantic import BaseModel, Field

class ServiceOrientedArchitecture(BaseModel):
    class Model(BaseModel):

        class Version(BaseModel):
            major: str = Field(default="1", description="Major version number")
            minor: str = Field(default="0", description="Minor version number")
            patch: str = Field(default="0", description="Patch version number")

            def __repr__(self):
                return self.__str__()
            def __str__(self):
                return f'_v{self.major}{self.minor}{self.patch}_'

        class Param(BaseModel):
            pass

        class Args(BaseModel):
            pass

        class Return(BaseModel):
            pass

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class Fibonacci(ServiceOrientedArchitecture):
    """
    Represents a Fibonacci computation service.
    """
    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: Literal['fast', 'slow'] = Field(
                default="fast", 
                description="Execution mode, either 'fast' or 'slow'."
            )

        class Args(BaseModel):
            n: int = Field(
                default=1, 
                description="The position of the Fibonacci number to compute."
            )

        class Return(BaseModel):
            n: int = Field(
                default=-1, 
                description="The computed Fibonacci number at position n."
            )

        @staticmethod
        def examples():
            """
            Provide example input sets for the Fibonacci service.
            """
            return [
                {"param": {"mode": "fast"}, "args": {"n": 13}}
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class PrimeNumberChecker(ServiceOrientedArchitecture):
    """
    Represents a prime number checking service.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            mode: Literal['basic', 'smart'] = Field(
                default="smart", 
                description="Check mode: 'basic' (brute force) or 'smart' (optimized)."
            )

        class Args(BaseModel):
            number: int = Field(
                default=13, 
                description="The number to check for primality."
            )

        class Return(BaseModel):
            is_prime: Optional[bool] = Field(
                default=None, 
                description="Whether the number is prime."
            )

        @staticmethod
        def examples():
            """
            Provide example input sets for the prime checker service.
            """
            return [
                {"param": {"mode": "smart"}, "args": {"number": 13}},
                {"param": {"mode": "basic"}, "args": {"number": 10}},
                {"param": {"mode": "smart"}, "args": {"number": 1}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class AddTwoNumbers(ServiceOrientedArchitecture):
    """
    Simple service to add two numbers.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            """
            Example Param: might control how the addition is performed (e.g., integer vs. float).
            """
            type: Literal['int', 'float'] = Field(
                default='int',
                description="Type of addition: 'int' or 'float'."
            )

            def is_float(self) -> bool:
                return self.type == 'float'

        class Args(BaseModel):
            a: int = Field(
                default=0,
                description="First number to add."
            )
            b: int = Field(
                default=0,
                description="Second number to add."
            )

        class Return(BaseModel):
            result: float = Field(
                default=0.0,
                description="Sum of the two numbers."
            )

        @staticmethod
        def examples():
            """
            Return example input sets for the AddTwoNumbers service.
            """
            return [
                {"param": {"type": "int"}, "args": {"a": 1, "b": 2}},
                {"param": {"type": "float"}, "args": {"a": 3, "b": 4}}
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        
class MultiplyTwoNumbers(ServiceOrientedArchitecture):
    """
    Simple service to multiply two numbers.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            """
            Example Param: might specify integer vs. float multiplication, or some advanced mode.
            """
            mode: Literal['basic', 'extended'] = Field(
                default='basic',
                description="Mode of multiplication."
            )

            def is_extended(self) -> bool:
                return self.mode == 'extended'

        class Args(BaseModel):
            x: int = Field(
                default=1,
                description="First number to multiply."
            )
            y: int = Field(
                default=1,
                description="Second number to multiply."
            )

        class Return(BaseModel):
            product: float = Field(
                default=1.0,
                description="Product of the two numbers."
            )
        @staticmethod
        def examples():
            """
            Return example input sets for the MultiplyTwoNumbers service.
            """
            return [
                {"param": {"mode": "basic"}, "args": {"x": 2, "y": 3}},
                {"param": {"mode": "extended"}, "args": {"x": 5, "y": 10}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        
class Factorial(ServiceOrientedArchitecture):
    """
    Computes the factorial of a given number.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            mode: Literal['iterative', 'recursive'] = Field(
                default='iterative',
                description="Computation mode: 'iterative' or 'recursive'."
            )

            def is_recursive(self) -> bool:
                return self.mode == 'recursive'

        class Args(BaseModel):
            n: int = Field(
                default=1,
                description="The number for which the factorial is computed."
            )

        class Return(BaseModel):
            result: int = Field(
                default=1,
                description="The factorial of n."
            )
        @staticmethod
        def examples():
            return [
                {"param": {"mode": "iterative"}, "args": {"n": 5}},
                {"param": {"mode": "recursive"}, "args": {"n": 6}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class SumOfSequence(ServiceOrientedArchitecture):
    """
    Computes the sum of a sequence of integers.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            inclusive: bool = Field(
                default=True,
                description="Whether the sequence is inclusive at the ends."
            )

        class Args(BaseModel):
            start: int = Field(
                default=1,
                description="Start of the sequence."
            )
            end: int = Field(
                default=1,
                description="End of the sequence."
            )

        class Return(BaseModel):
            total: int = Field(
                default=0,
                description="Sum of the sequence's integers."
            )
        @staticmethod
        def examples():
            return [
                {"param": {"inclusive": True}, "args": {"start": 1, "end": 5}},
                {"param": {"inclusive": False}, "args": {"start": 1, "end": 5}}
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class CircleAreaCalculator(ServiceOrientedArchitecture):
    """
    Calculates the area of a circle given its radius.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            units: Literal['cm', 'm'] = Field(
                default='cm',
                description="Units of measurement (centimeters or meters)."
            )

            def in_meters(self) -> bool:
                return self.units == 'm'

        class Args(BaseModel):
            radius: float = Field(
                default=1.0,
                description="Radius of the circle."
            )

        class Return(BaseModel):
            area: float = Field(
                default=0.0,
                description="Calculated area of the circle."
            )
        @staticmethod
        def examples():
            return [
                {"param": {"units": "cm"}, "args": {"radius": 5}},
                {"param": {"units": "m"}, "args": {"radius": 2}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class TriangleAreaCalculator(ServiceOrientedArchitecture):
    """
    Calculates the area of a triangle given its base and height.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            formula: Literal['basic', 'herons'] = Field(
                default='basic',
                description="Which formula to use: 'basic' (1/2 * base * height) or 'herons' formula."
            )

            def is_herons(self) -> bool:
                return self.formula == 'herons'

        class Args(BaseModel):
            base: float = Field(
                default=1.0,
                description="Base length of the triangle."
            )
            height: float = Field(
                default=1.0,
                description="Height of the triangle."
            )
            side_a: Optional[float] = Field(
                default=None,
                description="Side a for Heron's formula (if applicable)."
            )
            side_b: Optional[float] = Field(
                default=None,
                description="Side b for Heron's formula (if applicable)."
            )
            side_c: Optional[float] = Field(
                default=None,
                description="Side c for Heron's formula (if applicable)."
            )

        class Return(BaseModel):
            area: float = Field(
                default=0.0,
                description="Calculated area of the triangle."
            )
        @staticmethod
        def examples():
            return [
                {
                    "param": {"formula": "basic"}, 
                    "args": {"base": 10, "height": 5}
                },
                {
                    "param": {"formula": "herons"}, 
                    "args": {"side_a": 3, "side_b": 4, "side_c": 5}
                },
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class DataSorter(ServiceOrientedArchitecture):
    """
    Sorts a list of numeric data in ascending or descending order.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            order: Literal['asc', 'desc'] = Field(
                default='asc',
                description="Sorting order: 'asc' or 'desc'."
            )

            def is_descending(self) -> bool:
                return self.order == 'desc'

        class Args(BaseModel):
            data: list[float] = Field(
                default=[],
                description="A list of numeric values to sort."
            )

        class Return(BaseModel):
            sorted_data: list[float] = Field(
                default=[],
                description="The sorted list of numeric values."
            )
        @staticmethod
        def examples():
            return [
                {"param": {"order": "asc"}, "args": {"data": [3.1, 2.4, 10, 7]}},
                {"param": {"order": "desc"}, "args": {"data": [1, 2, 3, 4]}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class StatisticsCalculator(ServiceOrientedArchitecture):
    """
    Calculates basic statistics for a list of numeric data, such as mean, median, and mode.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            calc_mode: Literal['all', 'mean-only', 'median-only', 'mode-only'] = Field(
                default='all',
                description="Specifies which statistic(s) to compute."
            )

            def compute_mean(self) -> bool:
                return self.calc_mode in ('all', 'mean-only')

            def compute_median(self) -> bool:
                return self.calc_mode in ('all', 'median-only')

            def compute_mode(self) -> bool:
                return self.calc_mode in ('all', 'mode-only')

        class Args(BaseModel):
            data: list[float] = Field(
                default=[],
                description="A list of numeric values to analyze."
            )

        class Return(BaseModel):
            mean: Optional[float] = Field(
                default=None,
                description="Mean of the data."
            )
            median: Optional[float] = Field(
                default=None,
                description="Median of the data."
            )
            mode: Optional[float] = Field(
                default=None,
                description="Mode of the data (first mode if multiple)."
            )
        @staticmethod
        def examples():
            return [
                {"param": {"calc_mode": "all"}, "args": {"data": [1, 2, 2, 3, 4]}},
                {"param": {"calc_mode": "mean-only"}, "args": {"data": [10, 20, 30, 40]}},
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class DatabaseInsert(ServiceOrientedArchitecture):
    """
    Simulates inserting a record into a database.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            table_name: str = Field(
                default='default_table',
                description="Name of the table into which data will be inserted."
            )

        class Args(BaseModel):
            record: dict = Field(
                default_factory=dict,
                description="The record (dictionary) to insert."
            )

        class Return(BaseModel):
            success: bool = Field(
                default=False,
                description="Indicates if the insert operation was successful."
            )
            inserted_id: Optional[int] = Field(
                default=None,
                description="The ID of the newly inserted row, if successful."
            )
        @staticmethod
        def examples():
            return [
                {
                    "param": {"table_name": "users"}, 
                    "args": {"record": {"name": "John", "age": 30}}
                },
                {
                    "param": {"table_name": "orders"},
                    "args": {"record": {"user_id": 1, "product": "Book", "quantity": 2}}
                }
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

class DatabaseQuery(ServiceOrientedArchitecture):
    """
    Simulates querying records from a database.
    """
    class Model(ServiceOrientedArchitecture.Model):

        class Param(BaseModel):
            table_name: str = Field(
                default='default_table',
                description="Name of the table to query."
            )
            limit: int = Field(
                default=10,
                description="Maximum number of records to return."
            )

        class Args(BaseModel):
            filters: dict = Field(
                default_factory=dict,
                description="Filters to apply to the query (e.g., {'age': 30})."
            )

        class Return(BaseModel):
            records: list[dict] = Field(
                default_factory=list,
                description="List of records that match the query."
            )
            total_matched: int = Field(
                default=0,
                description="Total number of records that match the query."
            )
        @staticmethod
        def examples():
            return [
                {
                    "param": {"table_name": "users", "limit": 5},
                    "args": {"filters": {"age": 30}}
                },
                {
                    "param": {"table_name": "orders", "limit": 2},
                    "args": {"filters": {"product": "Book"}}
                }
            ]

        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()

def ret_to_args_convertor(ret: dict, args: dict) -> dict:
    """
    Simple placeholder function that converts a Fibonacci 'ret' object
    into a PrimeNumberChecker 'args' object. Extend or replace this logic
    as necessary.

    Parameters
    ----------
    ret : dict
        The Fibonacci return dictionary (e.g., {"n": 13}).
    args : dict
        The PrimeNumberChecker args dictionary (e.g., {"number": 0}).

    Returns
    -------
    dict
        An updated PrimeNumberChecker args dictionary.
    """
    # Example: If Fibonacci.ret.n -> PrimeNumberChecker.args.number
    # args['number'] = ret.get('n', 0)
    return args

def build_conversion_prompt(
    source_class: ServiceOrientedArchitecture, 
    target_class: ServiceOrientedArchitecture
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

    Returns
    -------
    tuple[str, str]
        A tuple of (prompt_text, generated_function_name).
    """
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
        from_class_version = from_class_version,
        to_class_version = to_class_version,
    )

    return prompt, f"{from_class_name}{from_class_version}_ret_to_{to_class_name}{from_class_version}_args_convertor"

def get_func_from_code(code_string,function_name):    
    # Execute the extracted code in a new local namespace
    local_namespace = {}
    exec(code_string, globals(), local_namespace)

    # Return the requested function from that namespace
    func = local_namespace.get(function_name)
    if not func:
        raise ValueError(f"Function '{function_name}' not found in the code.")

    return func

def get_code_from_gpt(prompt: str, function_name: str):
    """
    Given a prompt and a function name, this function calls the GPT API and
    extracts the code block containing the function. The code is then
    executed locally, and the specified function is returned as a callable.

    Parameters
    ----------
    prompt : str
        The prompt to send to GPT.
    function_name : str
        The name of the function to extract from GPT’s response.

    Returns
    -------
    tuple[str, callable]
        A tuple containing the extracted code string and the function object.

    Raises
    ------
    ValueError
        If no API key found, if the GPT response is invalid, or if the function
        is not found in the response.
    """
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("API key not found in environment variable 'OPENAI_API_KEY'")

    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    data = {
        "model": "gpt-4o-mini",
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

    return code_string, get_func_from_code(code_string,function_name)

def test_build(in_class = Fibonacci,out_class = PrimeNumberChecker):

    # Build prompt
    prompt_text, function_name = build_conversion_prompt(in_class, out_class)

    # Fetch code and function from GPT
    code_snippet, conversion_func = get_code_from_gpt(prompt_text, function_name)
    print(code_snippet)

    # Prepare sample data
    in_model_instance = in_class.Model()
    out_model_instance = out_class.Model()

    in_ret_data = in_model_instance.ret.model_dump()
    out_args_data = out_model_instance.args.model_dump()

    # Execute the GPT-provided conversion function
    updated_args = conversion_func(in_ret_data, out_args_data)
    return updated_args

    # print("Updated PrimeNumberChecker Args:", updated_args)

def _test_build_multi(in_class:ServiceOrientedArchitecture,
                     out_class:ServiceOrientedArchitecture,
                     in_ret_list=[], out_args_list=[]):
    # Build prompt
    prompt_text, function_name = build_conversion_prompt(in_class, out_class)

    # Fetch code and function from GPT
    code_snippet, conversion_func = get_code_from_gpt(prompt_text, function_name)
    print(code_snippet)

    # Generate default test data if none provided
    in_model_instance:ServiceOrientedArchitecture.Model = in_class.Model()
    in_ret_list = [in_model_instance.Return(**i).model_dump() for i in in_ret_list]

    out_model_instance = out_class.Model()
    out_args_list = [out_model_instance.Args(**i).model_dump() for i in out_args_list]
    target_args_list = [dict(**i) for i in out_args_list]

    results = []
    # Iterate over all combinations of ret and args
    for in_ret_data,out_args_data,target_args_data in zip(in_ret_list,out_args_list,target_args_list):
        try:
            updated_args:dict = conversion_func(in_ret_data, out_args_data)
            for k,v in updated_args.items():
                if v!=target_args_data[k]:
                    raise ValueError(f'convert error of {in_ret_data} to {target_args_data}')
            results.append(updated_args)
        except Exception as e:
            results.append({"error": str(e)})

    return results

def test_build_multi(in_ret_samples,target_args_samples,
                     in_class:ServiceOrientedArchitecture,
                     out_class:ServiceOrientedArchitecture,):
    results = _test_build_multi(in_class, out_class, in_ret_samples, target_args_samples)
    for idx, res in enumerate(results):
        print(f"Test case {idx+1}: from {in_ret_samples[idx]} to {res}")


if __name__ == "__main__":
    # # Test 1: Fibonacci -> PrimeNumberChecker
    # fib_to_prime_args = test_build(Fibonacci, PrimeNumberChecker)
    # print("Fibonacci -> PrimeNumberChecker:", fib_to_prime_args)

    # # Test 2: AddTwoNumbers -> MultiplyTwoNumbers
    # add_to_multiply_args = test_build(AddTwoNumbers, MultiplyTwoNumbers)
    # print("AddTwoNumbers -> MultiplyTwoNumbers:", add_to_multiply_args)

    # # Test 3: Factorial -> SumOfSequence
    # factorial_to_sum_args = test_build(Factorial, SumOfSequence)
    # print("Factorial -> SumOfSequence:", factorial_to_sum_args)

    # # Test 4: CircleAreaCalculator -> TriangleAreaCalculator
    # circle_to_triangle_args = test_build(CircleAreaCalculator, TriangleAreaCalculator)
    # print("CircleAreaCalculator -> TriangleAreaCalculator:", circle_to_triangle_args)

    # # Test 5: DataSorter -> StatisticsCalculator
    # sorter_to_stats_args = test_build(DataSorter, StatisticsCalculator)
    # print("DataSorter -> StatisticsCalculator:", sorter_to_stats_args)

    # # Test 6: DatabaseInsert -> DatabaseQuery
    # db_insert_to_query_args = test_build(DatabaseInsert, DatabaseQuery)
    # print("DatabaseInsert -> DatabaseQuery:", db_insert_to_query_args)

    # Example: test with manually defined ret and args lists
    test_build_multi(
        in_ret_samples = [
            {"n": 5},   # Sample 1 for Fibonacci
            {"n": 10},  # Sample 2
        ],
        target_args_samples = [
            {"number": 5},  # Sample 1 for PrimeNumberChecker
            {"number": 10},  # Sample 2
        ]
        ,in_class=Fibonacci, out_class=PrimeNumberChecker)

    # Input: results from AddTwoNumbers
    test_build_multi(
        in_ret_samples = [
            {"result": 8.0},   # Expect x=4, y=4
            {"result": 15.0},  # Expect x=7, y=8 or some close combo
            {"result": 1.0},   # Edge case: x=0, y=1
        ],
        # Target args to check conversion correctness
        target_args_samples = [
            {"x": 8, "y": 1},
            {"x": 15, "y": 1},
            {"x": 1, "y": 1},
        ],in_class=AddTwoNumbers, out_class=MultiplyTwoNumbers)
    
    # Factorial ➝ SumOfSequence
    test_build_multi(
        in_ret_samples = [
            {"result": 6},   # factorial(3) = 6
            {"result": 24},  # factorial(4) = 24
        ],
        target_args_samples = [
            {"start": 1, "end": 6},
            {"start": 1, "end": 24},
        ],
        in_class=Factorial,
        out_class=SumOfSequence
    )
