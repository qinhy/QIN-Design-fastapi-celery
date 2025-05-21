import json
import time
from celery.result import AsyncResult
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from Task.Basic import ServiceOrientedArchitecture
from .utils import MermaidGraph


class TaskDAGRunner(ServiceOrientedArchitecture):

    @classmethod
    def description(cls):
        return "Executes tasks defined as nodes in a DAG using the structure of a Mermaid graph."

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            pass

        class Args(BaseModel):
            mermaid_graph_text: str = Field(..., description="Mermaid graph text defining the DAG")

        class Return(BaseModel):
            results: Dict[str, Any] = {}

        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass

        class Version(ServiceOrientedArchitecture.Model.Version):
            pass

        @staticmethod
        def examples():
            return [
    {'args': {'mermaid_graph_text': '''
graph TD
    Fibonacci_1["{'param': {'mode': 'fast'},'args': {'n': 7}}"]
    Fibonacci_2["{'param': {'mode': 'fast'}}"]
    PrimeNumberChecker["{'param': {'mode': 'smart'}}"]

    Fibonacci_1 --> Fibonacci_2
    Fibonacci_2 -- "{'n': 'number'}" --> PrimeNumberChecker
    Fibonacci_2 -- "{'n': 'n'}" --> BinaryRepresentation
                         
'''}},
    {'args': {'mermaid_graph_text': '''
              
graph TD
    Fibonacci_1["{'args': {'n': 1}, 'param': {'mode': 'fast'}}"]
    Fibonacci_3["{'args': {'n': 3}, 'param': {'mode': 'fast'}}"]

    Fibonacci_1 --> Fibonacci_2
    Fibonacci_2 --> Fibonacci_4
    Fibonacci_3 -- "{'n':'numbers'}" --> AddNumbers_1
    Fibonacci_4 -- "{'n':'numbers'}" --> AddNumbers_1

    AddNumbers_1 -- "{'sum':'n'}" --> Fibonacci_5
    AddNumbers_1 -- "{'sum':'numbers'}" --> AddNumbers_2
    Fibonacci_2 -- "{'n':'numbers'}" --> AddNumbers_2

    Fibonacci_5 --> Fibonacci_6
    AddNumbers_2 -- "{'sum':'numbers'}" --> AddNumbers_3
    Fibonacci_5 -- "{'n':'numbers'}" --> AddNumbers_3
              
'''}},
]

        version: Version = Version()
        param: Param = Param()
        args: Args
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        ACTION_REGISTRY = {}

        def __init__(self, model: 'TaskDAGRunner.Model', BasicApp=None, level=None):
            super().__init__(model, BasicApp, level)
            self.model = model
            self.logger = self.model.logger

        def __call__(self) -> 'TaskDAGRunner.Model':
            """
            Parse the DAG, submit each task in topological order,
            and collect the final results.
            """
            graph = MermaidGraph(self.model.args.mermaid_graph_text)
            order = graph.get_pipeline_order()
            configs, mappings = graph.get_pipeline_config()[::2], graph.get_pipeline_config()[1::2]

            # Build maps for quick lookup
            config_map = {node: cfg for node, cfg in zip(order, configs)}
            mapping_map = {node: mp for node, mp in zip(order[1:], mappings)}

            task_ids: Dict[str, str] = {}
            cache: Dict[str, Any] = {}

            for node in order:
                payload = self._build_payload(node, config_map[node], graph, cache, task_ids, mapping_map)
                task_name = node.split("_", 1)[0]
                task_ids[node] = self._submit(task_name, payload)

            results = self._collect_results(order, graph, task_ids)
            # if single end-node, unwrap the dict
            final = results if len(results) > 1 else next(iter(results.values()))

            self.model.ret = self.model.Return(results=final)
            return self.model

        def get_args_schema(self, node):
            """
            Retrieve the args schema for a given task.
            """
            return self.ACTION_REGISTRY[node.split("_", 1)[0]
                    ].as_openai_tool(
                    )["function"]["parameters"]["properties"]["args"]["properties"]

        def _build_payload(
            self,
            node: str,
            config: Dict[str, Any],
            graph: MermaidGraph,
            cache: Dict[str, Any],
            task_ids: Dict[str, str],
            mapping_map: Dict[str, Any],
        ) -> Dict[str, Any]:
            """
            Merge the static config with any inputs from parent tasks.
            """
            # Get parents of the current node from the graph structure
            parents = graph.graph[node]["prev"]
            # Start with a shallow copy of static config for the current node
            payload = dict(config)

            if parents:
                inputs = {}
                parent_results = []
                # For each mapping related to this node
                for m in mapping_map.get(node, []):
                    parent = m["from"]
                    mapping = m.get("map")
                    # Fetch parent result from cache, or retrieve and cache it if missing
                    if parent not in cache:
                        cache[parent] = self._fetch_result(task_ids[parent])
                    parent_result = cache[parent]
                    if mapping:
                        # If there’s a field mapping, store for later mapping application
                        parent_results.append((parent, parent_result, mapping))
                    else:
                        # If no mapping, merge parent result directly into inputs
                        inputs.update(parent_result)

                ##################### all_mappings checking #####################
                all_mappings = []
                for parent_name, parent_result, mapping in parent_results: 
                    for src, dst in mapping.items():
                        all_mappings.append((f'{parent_name}:{src}', dst))

                # all_mappings: List of (parent:source, destination) pairs, e.g. [('ParentA:foo', 'z'), ...]

                all_src = [src for src, dst in all_mappings]
                all_dst = [dst for src, dst in all_mappings]

                # Example scenarios:
                # - one2one: [('ParentA:foo', 'x'), ('ParentB:bar', 'y')]
                # - many2one: [('ParentA:foo', 'z'), ('ParentB:bar', 'z')
                # - one2many: [('ParentA:foo', 'x'), ('ParentA:foo', 'y')
                # - many2many: [('ParentA:foo', 'z'), ('ParentA:foo', 'y'), ('ParentB:bar', 'z')]

                if len(all_src) != len(set(all_src)) and len(all_dst) != len(set(all_dst)):
                    flag = 'many2many'    # Multiple overlaps in both sources and destinations
                    raise NotImplementedError(f"[NotImplementedError]: Multiple overlaps in both sources and destinations: {all_mappings}")
                elif len(all_dst) != len(set(all_dst)):
                    flag = 'many2one'     # Multiple sources map to the same destination
                elif len(all_src) != len(set(all_src)):
                    flag = 'one2many'     # One source maps to multiple destinations
                else:
                    flag = 'one2one'      # Pure 1:1 mapping

                print(f"Mapping flag: {flag}")

                ##################### apply mapping #####################
                if flag == 'many2one':
                    # Example: mapping [('ParentA:foo', 'z'), ('ParentB:bar', 'z')]
                    # Both foo (from ParentA) and bar (from ParentB) map to 'z'
                    the_one = all_dst[0]
                    the_one_schema = self.get_args_schema(node)[the_one]

                    if the_one_schema["type"] == "array":
                        # Collect all source values into a list for 'z'
                        element_type = the_one_schema["items"]["type"]
                        inputs[the_one] = []
                        for parent_name, parent_result, mapping in parent_results:
                            for src, dst in mapping.items():
                                if dst == the_one:
                                    value = parent_result.get(src)
                                    # Optionally, validate type here
                                    if value is not None:
                                        inputs[the_one].append(value)

                        # Optionally: type check each element
                        if element_type == "string":
                            inputs[the_one] = [str(v) for v in inputs[the_one]]
                        elif element_type == "integer":
                            inputs[the_one] = [int(v) for v in inputs[the_one]]
                        elif element_type == "number":
                            inputs[the_one] = [float(v) for v in inputs[the_one]]
                        else:
                            raise NotImplementedError(f"[NotImplementedError]: Unsupported type '{the_one_schema['type']}' for field '{the_one}'.")

                    elif the_one_schema["type"] == "string":
                        # If schema expects a string but multiple values provided, join with separator
                        values = []
                        for parent_name, parent_result, mapping in parent_results:
                            for src, dst in mapping.items():
                                if dst == the_one:
                                    value = parent_result.get(src)
                                    if value is not None:
                                        values.append(str(value))

                        # Join values (customize separator as needed)
                        inputs[the_one] = "".join(values)

                    else:
                        # Default behavior: last value wins (or raise error)
                        for parent_name, parent_result, mapping in parent_results:
                            for src, dst in mapping.items():
                                if dst == the_one:
                                    value = parent_result.get(src)
                                    if value is not None:
                                        inputs[the_one] = value
                        print(f"Warning: 'many2one' mapping for field '{the_one}' with unsupported type '{the_one_schema['type']}', used last value.")

                    payload["args"] = inputs

                else:
                    # For one2one and one2many mappings
                    # Example: mapping [('ParentA:foo', 'x'), ('ParentB:bar', 'y')] (one2one)
                    # Example: mapping [('ParentA:foo', 'x'), ('ParentA:foo', 'y')] (one2many)
                    for parent_name, parent_result, mapping in parent_results:
                        all_dst = [dst for src, dst in mapping.items()]

                        # Map fields from parent result to our inputs dict using the mapping
                        for src, dst in mapping.items():
                            if dst in inputs:
                                print(f"Warning: Overwriting input field '{dst}' with value from parent '{parent_name}'. Previous value: {inputs[dst]}, New value: {parent_result.get(src)}")
                            if src not in parent_result:
                                print(f"Warning: Source key '{src}' not found in parent result from '{parent_name}'.")
                            else:
                                inputs[dst] = parent_result[src]

                        unused_fields = set(parent_result.keys()) - set(mapping.keys())
                        if unused_fields:
                            print(f"Unused fields from parent '{parent_name}': {unused_fields}")

                    # Set the merged inputs as the "args" key in payload
                    payload["args"] = inputs

            return payload


        def _submit(self, task_name: str, payload: Dict[str, Any]) -> str:
            """
            Submit a task via the BasicApp API and return its task_id.
            """
            self._log(f"Submitting {task_name!r} with payload {payload}")
            resp = self.BasicApp.parent.api_perform_action(task_name, payload)
            return resp["task_id"]

        def _wait(self, task_id: str, timeout: int = 30) -> AsyncResult:
            """
            Poll the Celery AsyncResult until success or failure.
            """
            deadline = time.time() + timeout
            result = AsyncResult(task_id)

            while time.time() < deadline:
                if result.state == "SUCCESS":
                    return result
                if result.state in ("FAILURE", "REVOKED"):
                    raise RuntimeError(f"Task {task_id} failed: {result.result}")
                time.sleep(1)

            raise TimeoutError(f"Task {task_id} did not finish in {timeout}s")

        def _fetch_result(self, task_id: str) -> Any:
            """
            Retrieve and decode the task result payload.
            """
            self._wait(task_id)
            raw = self.BasicApp.get_task_meta(task_id)["result"]
            decoded = self.BasicApp.parent.task_result_decode_as_jsonStr(raw)
            return json.loads(decoded)["ret"]

        def _collect_results(
            self,
            order: list,
            graph: MermaidGraph,
            task_ids: Dict[str, str],
        ) -> Dict[str, Any]:
            """
            Gather results for all end-nodes in the DAG.
            """
            ends = [n for n in order if not graph.graph[n]["next"]]
            return {n: self._fetch_result(task_ids[n]) for n in ends}

        def to_stop(self) -> 'TaskDAGRunner.Model':
            self._log("Stop flag detected; returning 0.", level=TaskDAGRunner.Levels.WARNING)
            self.model.ret = self.model.Return(results=0)
            return self.model

        def _log(self, message: str, level=None) -> None:
            """
            Log locally and send a telemetry event.
            """
            lvl = level or self.logger.level
            self.logger.log(lvl, message)
            self.send_data_to_task({lvl: message})
