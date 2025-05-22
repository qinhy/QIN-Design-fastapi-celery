import json
import time
from celery.result import AsyncResult
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

try:
    from Task.Basic import ServiceOrientedArchitecture
    from .utils import MermaidGraph
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture
    from utils import MermaidGraph


MermaidEditorHtml = """
<!DOCTYPE html>
<html>

<head>
    <title>Mermaid Editor</title>
</head>

<body>
    <textarea id="mermaid-input" style="width: 100%; height: 300px;"></textarea>
    <div id="mermaid-output"></div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        const STORAGE_KEY = 'mermaid-diagram';
        const mermaidInput = document.getElementById('mermaid-input');
        const mermaidOutput = document.getElementById('mermaid-output');
        mermaid.initialize({ startOnLoad: false });        // Load saved diagram from localStorage
        const savedDiagram = localStorage.getItem(STORAGE_KEY);
        if (savedDiagram) {
            mermaidInput.value = savedDiagram;
        } else {
            mermaidInput.value = `
graph LR
    A[Start] --> B{Is it?}
    B -- Yes --> C[OK]
    B -- No --> D[KO]
    C --> E[End]
    D --> E`;
        }
        async function renderMermaid() {
            const code = mermaidInput.value;
            try {
                const { svg } = await mermaid.render('generatedDiagram', code);
                mermaidOutput.innerHTML = svg;
            } catch (err) {
                mermaidOutput.innerHTML = `<pre style="color:red;">${err.message}</pre>`;
            }
        }        // Save input to localStorage and re-render on change
        mermaidInput.addEventListener('input', () => {
            localStorage.setItem(STORAGE_KEY, mermaidInput.value);
            renderMermaid();
        });        // Initial render
        renderMermaid();
    </script>
</body>

</html>
"""

class TaskDAGRunner(ServiceOrientedArchitecture):
    MermaidEditorHtml = MermaidEditorHtml
    @classmethod
    def description(cls):
        return "Executes tasks defined as nodes in a DAG using the structure of a Mermaid graph."

    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        class Param(BaseModel):
            str_customize_separator: str = Field(
                default=",", description="Customize the separator used when joining multiple values for a field.")

        class Args(BaseModel):
            mermaid_graph_text: str = Field(..., description="Mermaid graph text defining the DAG")

        class Return(BaseModel):
            results: Dict[str, dict] = Field(
                    default_factory=dict, description="Final results (decoded from json string) of the DAG execution")
            execution_order: list = Field(
                    default_factory=list, description="Topological execution order")
            graph: Optional[dict] = Field(
                    None, description="Original Mermaid graph string dict.")


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
            self.model:TaskDAGRunner.Model = model
            self.logger = self.model.logger

        def __call__(self) -> 'TaskDAGRunner.Model':
            """
            Parse the DAG, submit each task in topological order,
            and collect the final results.
            """
            self.model.ret.graph = graph = MermaidGraph(self.model.args.mermaid_graph_text)
            self.model.ret.execution_order = order = graph.get_pipeline_order()
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
            payload = dict(config)
            parents = graph.graph[node]["prev"]
            if not parents: return payload

            payload["args"] = inputs = {}
            parent_results = self._collect_parent_results(
                                    node, mapping_map, cache, task_ids)

            if not parent_results: return payload

            all_mappings = self._flatten_mappings(parent_results)
            mapping_flag = self._determine_mapping_flag(all_mappings)
            # print(f"Mapping flag: {mapping_flag}")

            if mapping_flag == "many2many":
                raise NotImplementedError(f"[NotImplementedError]: Multiple overlaps in both sources and destinations: {all_mappings}")

            if mapping_flag == "many2one":
                inputs.update(
                    self._handle_many2one_mapping(node, parent_results, all_mappings))
            else:
                inputs.update(
                    self._handle_one2one_or_one2many_mapping(parent_results))

            payload["args"] = inputs
            return payload

        def _collect_parent_results(self, node, mapping_map, cache, task_ids):
            parent_results = []
            # For each mapping related to this node
            for m in mapping_map.get(node, []):
                parent = m["from"]
                mapping = m.get("map")
                # Fetch parent result from cache, or retrieve and cache it if missing
                if parent not in cache:
                    cache[parent] = self._fetch_result(task_ids[parent])
                parent_result:dict = cache[parent]
                if mapping is None:
                    mapping = {k:k for k in parent_result.keys()}
                parent_results.append((parent, parent_result, mapping))
            return parent_results

        def _flatten_mappings(self, parent_results):
            return [
                (f"{parent}:{src}", dst)
                for parent, _, mapping in parent_results
                for src, dst in mapping.items()
            ]

        def _determine_mapping_flag(self, mappings):
            srcs, dsts = zip(*mappings) if mappings else ([], [])
            src_set, dst_set = set(srcs), set(dsts)

            if len(srcs) != len(src_set) and len(dsts) != len(dst_set):
                return "many2many"
            elif len(dsts) != len(dst_set):
                return "many2one"
            elif len(srcs) != len(src_set):
                return "one2many"
            return "one2one"

        def _handle_many2one_mapping(self, node, parent_results, all_mappings):
            field = all_mappings[0][1]
            schema = self.get_args_schema(node)[field]
            values = []

            for parent, result, mapping in parent_results:
                for src, dst in mapping.items():
                    if dst == field and (val := result.get(src)) is not None:
                        values.append(val)

            if schema["type"] == "array":
                return {field: self._convert_array(values, schema["items"]["type"])}
            elif schema["type"] == "string":
                return {field: self.model.param.str_customize_separator.join(map(str, values))}
            else:
                print(f"Warning: 'many2one' mapping for field '{field}' with unsupported type '{schema['type']}', used last value.")
                return {field: values[-1]} if values else {}

        def _convert_array(self, values, element_type):
            converters = {"string": str, "integer": int, "number": float}
            converter = converters.get(element_type)
            if not converter:
                raise NotImplementedError(f"[NotImplementedError]: Unsupported array element type '{element_type}'")
            return [converter(v) for v in values]

        def _handle_one2one_or_one2many_mapping(self, parent_results):
            inputs = {}
            for parent, result, mapping in parent_results:
                for src, dst in mapping.items():
                    if dst in inputs:
                        print(f"Warning: Overwriting input field '{dst}' from parent '{parent}'. Previous value: {inputs[dst]}, New value: {result.get(src)}")
                    if src not in result:
                        print(f"Warning: Source key '{src}' not found in parent result from '{parent}'.")
                    else:
                        inputs[dst] = result[src]

                unused_fields = set(result.keys()) - set(mapping.keys())
                if unused_fields:
                    print(f"Unused fields from parent '{parent}': {unused_fields}")
            return inputs


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
            time.sleep(0.5)
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
