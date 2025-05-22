from celery import chain, group, chord
from typing import Dict, List, Any
from collections import defaultdict
import re
import json
from collections import defaultdict, deque
from typing import Any, Dict, List
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class MermaidGraph:
    """
    Mermaid Graph Protocol
    """

    TEST_GRAPH = """
    graph TD
        Fibonacci_01["{'args': {'n': 10}, 'param': {'mode': 'fast'}}"]
        PrimeNumberChecker["{'param': {'mode': 'smart'}}"]
        BinaryRepresentation["{'param': {'bit_length': 8}}"]
        ChatGPTService["{'args': {'user_prompt': 'Is this number interesting?'}, 'param': {'model': 'gpt-4o-mini'}}"]

        Fibonacci_01 -- "{'result':'number'}" --> PrimeNumberChecker
        PrimeNumberChecker --> BinaryRepresentation
        BinaryRepresentation --> ChatGPTService
    """
    """
    ### 📌 Mermaid Graph Protocol (for beginners):

    * graph TD → Start of a top-down Mermaid flowchart
    * NodeName[_optionalID]["{{...}}"] (e.g., ResizeImage_01) → Define a node with initialization parameters in JSON-like format
    * The initialization parameters **must not contain mapping information** — only raw valid values (e.g., numbers, strings, booleans)
    * A --> B → Connect node A to node B (no field mapping)
    * A -- "{{'x':'y'}}" --> B → Map output field 'x' from A to input field 'y' of B
    * Use **valid field names** from each tool's input/output schema
    """    
    def __init__(self, mermaid_text: str=None):
        if mermaid_text is None:
            mermaid_text = MermaidGraph.TEST_GRAPH
        self.graph = self.parse_mermaid(mermaid_text)

    def parse_mermaid(self, mermaid_text: str=None) -> dict:
        lines = [l.strip() for l in mermaid_text.strip().splitlines()]
        lines = [l for l in lines if ('["{' in l) or ('--' in l)]
        lines = [l for l in lines if '["{}"]' not in l]
        lines = [l for l in lines if not l.startswith('%%')]
        graph = defaultdict(lambda: {"prev": [], "next": [], "config": {}, "maps": {}})

        node_pattern = re.compile(r'^([\w-]+)\s*\[\s*"(.+)"\s*\]$')
        map_pattern = re.compile(r'^([\w-]+)\s*--\s*"(.*?)"\s*-->\s*([\w-]+)$')
        simple_pattern = re.compile(r'^([\w-]+)\s*-->\s*([\w-]+)$')

        def parse_json(s: str) -> Any:
            try:
                return json.loads(s.replace("'", '"'))
            except Exception as e:
                print(s)
                raise e

        for l in lines:
            if not l or l.startswith("graph"):
                continue
            m = node_pattern.match(l)
            if m:
                node, cfg = m.groups()
                parsed = parse_json(cfg)
                if parsed is not None:
                    graph[node]["config"] = parsed
                continue
            m = map_pattern.match(l)
            if m:
                src, cfg, dst = m.groups()
                graph[src]["next"].append(dst)
                graph[dst]["prev"].append(src)
                parsed = parse_json(cfg)
                if parsed is not None:
                    graph[src]["maps"][dst] = parsed
                continue
            m = simple_pattern.match(l)
            if m:
                src, dst = m.groups()
                graph[src]["next"].append(dst)
                graph[dst]["prev"].append(src)
                continue
            raise ValueError(f"Invalid Mermaid syntax: {l}")

        return dict(graph)


    def get_pipeline_order(self) -> List[str]:
        """Return the node names in topological order."""
        indegree = {node: len(data["prev"]) for node, data in self.graph.items()}
        queue = deque([node for node, deg in indegree.items() if deg == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self.graph[node]["next"]:
                indegree[neighbor] -= 1
                if indegree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.graph):
            raise ValueError("Cycle detected in Mermaid graph")
        return order

    def get_pipeline_config(self) -> List[Any]:
        """
        Returns:
            A list structured like:
            [config_node_1, [maps_to_node_2], config_node_2, [maps_to_node_3], config_node_3, ...]
            
            Where maps_to_node_N is a list of mappings from each of its parent nodes.
            Each item: { "from": <src_node>, "map": {field_map} } or None
        """
        order = self.get_pipeline_order()
        config = []

        for i, node in enumerate(order):
            # Add this node's config
            config.append(self.graph[node]["config"])

            # If this is not the last node, we prepare its input mappings
            if i < len(order) - 1:
                next_node = order[i + 1]
                incoming_maps = []
                for prev in self.graph[next_node]["prev"]:
                    mapping = self.graph[prev]["maps"].get(next_node, None)
                    incoming_maps.append({"from": prev, "map": mapping})
                config.append(incoming_maps if incoming_maps else None)

        return config


    def get_pipeline_services(self, match_registry: List[str]) -> List[str]:
        """Best-effort match node names to service names in ACTION_REGISTRY."""
        order = self.get_pipeline_order()
        matched = []
        for node in order:
            service = next((svc for svc in match_registry if svc.lower() in node.lower()), None)
            if not service:
                raise ValueError(f"No matching service found for node '{node}'")
            matched.append(service)
        return matched

    def get_pipeline_mappings(self) -> List[List[Dict[str, Any]]]:
        """
        Returns:
            A list of lists where each sublist contains mapping dictionaries for all incoming edges to a node.
            Each mapping dict: {"from": <source_node>, "map": <field_mapping or None>}
        """
        order = self.get_pipeline_order()
        mappings = []

        for i in range(1, len(order)):
            current_node = order[i]
            incoming = []
            for prev_node in self.graph[current_node]["prev"]:
                incoming.append({
                    "from": prev_node,
                    "map": self.graph[prev_node]["maps"].get(current_node, None)
                })
            mappings.append(incoming)

        return mappings

def build_execution_dag(graph, task_registry: Dict[str, Any], config: List[Any]):
    """
    Build a Celery DAG using chain, group, and chord from a MermaidGraph + config.

    Returns:
        final Celery signature (chain or chord)
    """
    top_order = graph.get_pipeline_order()
    step_outputs = {}  # node_name -> Celery signature
    node_configs = config[::2]
    node_mappings = config[1::2]

    node_config_map = {name: node_configs[i] for i, name in enumerate(top_order)}
    node_map_inputs = defaultdict(list)  # node → list of {"from": src, "map": dict}

    # Reverse mappings from config list
    for i, node in enumerate(top_order[1:]):
        node_map_inputs[node] = node_mappings[i]

    for i, node in enumerate(top_order):
        task = task_registry.get(node.split("_")[0], None)
        if task is None:
            raise ValueError(f"No Celery task found for node: {node}")

        current_config = node_config_map[node]
        parents = graph.graph[node]["prev"]

        if not parents:
            # Independent source node
            step_outputs[node] = task.s(current_config)
        elif len(parents) == 1:
            # Chain from single parent
            parent_node = parents[0]
            parent_sig = step_outputs[parent_node]
            step_outputs[node] = parent_sig | task.s(current_config)
        else:
            # Multi-input: use chord(group(...), task.s(config))
            parent_sigs = [step_outputs[p] for p in parents]
            parent_maps = node_map_inputs[node]
            if len(parents) != len(parent_maps):
                raise ValueError(f"Mapping mismatch for node {node}: {parents} vs {parent_maps}")
            # step_outputs[node] = chord(parent_sigs, task.s(current_config))
            step_outputs[node] = group(parent_sigs) | task.s(current_config)
            print(step_outputs)

    # Determine final output step(s)
    end_nodes = [n for n in top_order if not graph.graph[n]["next"]]
    if len(end_nodes) == 1:
        res = step_outputs[end_nodes[0]]
    else:
        res = group([step_outputs[n] for n in end_nodes])
    
    return res

from celery import chain, group, chord
from collections import defaultdict
from typing import Dict, List, Any

def build_execution_dag(graph, task_registry: Dict[str, Any], config: List[Any]):
    """
    Build a Celery DAG using chain, group, and chord from a MermaidGraph + config.

    Returns:
        final Celery signature (chain or group)
    """
    top_order = graph.get_pipeline_order()
    node_configs = config[::2]
    node_mappings = config[1::2]
    node_config_map = {name: node_configs[i] for i, name in enumerate(top_order)}
    node_map_inputs = defaultdict(list)

    for i, node in enumerate(top_order[1:]):
        node_map_inputs[node] = node_mappings[i]

    step_signatures = {}  # node → Celery Signature (chain or chord)

    for node in top_order:
        task = task_registry.get(node.split("_")[0])
        if not task:
            raise ValueError(f"No task registered for: {node}")

        config_data = node_config_map[node]
        parents = graph.graph[node]["prev"]

        if not parents:
            # Leaf node (no inputs)
            step_signatures[node] = task.s(config_data)
        elif len(parents) == 1:
            # Single parent — chain from it
            parent_sig = step_signatures[parents[0]]
            step_signatures[node] = parent_sig | task.s(config_data)
        else:
            # Multi-input — collect parent signatures
            parent_group = []
            for idx, parent in enumerate(parents):
                parent_sig = step_signatures[parent]
                parent_group.append(parent_sig)

            # Build chord with collected inputs
            step_signatures[node] = chord(group(parent_group), task.s(config_data))

    # Determine final output
    end_nodes = [n for n in top_order if not graph.graph[n]["next"]]
    final_dag = None
    if len(end_nodes) == 1:
        final_dag = step_signatures[end_nodes[0]]
    else:
        final_dag = group([step_signatures[n] for n in end_nodes])

    return final_dag, step_signatures

from celery import chain, group, chord
from collections import defaultdict, Counter

def build_execution_dag(graph, task_registry, config, store_task, load_task):
    top_order = graph.get_pipeline_order()
    node_configs = config[::2]
    node_mappings = config[1::2]

    node_config_map = {name: node_configs[i] for i, name in enumerate(top_order)}
    node_map_inputs = defaultdict(list)
    for i, node in enumerate(top_order[1:]):
        node_map_inputs[node] = node_mappings[i]

    # 1. Count usage of each node
    usage_count = Counter()
    for node, data in graph.graph.items():
        for parent in data["prev"]:
            usage_count[parent] += 1

    # 2. Build steps
    step_signatures = {}
    load_redirects = {}

    for node in top_order:
        task = task_registry.get(node.split("_")[0])
        if not task:
            raise ValueError(f"No task found for: {node}")

        config_data = node_config_map[node]
        parents = graph.graph[node]["prev"]

        if not parents:
            # Leaf node
            step = task.s(config_data)
            if usage_count[node] > 1:
                tag = f"{node}:shared"
                step = chain(step, store_task.s(tag), load_task.s(tag))  # ✅ ensures order
                load_redirects[node] = load_task.s(tag)

            step_signatures[node] = step
            continue

        # Gather parent signatures
        parent_sigs = []
        for idx, parent in enumerate(parents):
            if parent in load_redirects:
                parent_sigs.append(load_redirects[parent])
            else:
                parent_sigs.append(step_signatures[parent])

        # Chaining logic
        if len(parent_sigs) == 1:
            step = parent_sigs[0] | task.s(config_data)
        else:
            step = chord(group(parent_sigs), task.s(config_data))

        if usage_count[node] > 1:
            tag = f"{node}:shared"
            step = chain(step, store_task.s(tag))
            load_redirects[node] = load_task.s(tag)

        step_signatures[node] = step

    # 3. Final output
    end_nodes = [n for n in top_order if not graph.graph[n]["next"]]
    if len(end_nodes) == 1:
        return step_signatures[end_nodes[0]], step_signatures
    else:
        return group([step_signatures[n] for n in end_nodes]), step_signatures

from celery import Celery, Task
from time import sleep
import random

app = Celery('mock_pipeline', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

def mock_output(name, delay=0.2):
    def wrapper(config):
        sleep(delay)  # simulate work
        print(f"✅ {name} executed with config: {config}")
        return {f"{name.lower()}_output": random.randint(100, 999)}
    return wrapper

@app.task(name="StoreSharedResult")
def StoreSharedResult(tag: str, data: dict):
    redis_client.set(tag, json.dumps(data))
    return tag  # pass the tag forward if needed

@app.task(name="LoadSharedResult")
def LoadSharedResult(tag: str):
    return json.loads(redis_client.get(tag))

@app.task(name="LoadCSV")
def LoadCSV(config):
    return mock_output("LoadCSV")(config)

@app.task(name="LoadJSON")
def LoadJSON(config):
    return mock_output("LoadJSON")(config)

@app.task(name="CleanData")
def CleanData(config):
    return mock_output("CleanData")(config)

@app.task(name="Normalize")
def Normalize(config):
    return mock_output("Normalize")(config)

@app.task(name="MergeData")
def MergeData(config):
    return mock_output("MergeData")(config)

@app.task(name="FeatureExtract")
def FeatureExtract(config):
    return mock_output("FeatureExtract")(config)

@app.task(name="MLModel")
def MLModel(config):
    return mock_output("MLModel")(config)

@app.task(name="ExplainModel")
def ExplainModel(config):
    return mock_output("ExplainModel")(config)

@app.task(name="ArchiveOutput")
def ArchiveOutput(config):
    return mock_output("ArchiveOutput")(config)

@app.task(name="ChatGPT")
def ChatGPT(config):
    return mock_output("ChatGPT")(config)

if __name__ == "__main__":
    mermaid_text = """    
graph TD
    LoadCSV["{'args': {'path': 'data.csv'}}"]
    LoadJSON["{'args': {'path': 'metadata.json'}}"]
    CleanData["{'param': {'strategy': 'dropna'}}"]
    Normalize["{'param': {'method': 'zscore'}}"]
    MergeData["{'param': {'on': 'id'}}"]
    FeatureExtract["{'param': {'features': ['mean', 'std', 'max']}}"]
    MLModel["{'param': {'model_type': 'XGBoost', 'max_depth': 5}}"]
    ExplainModel["{'param': {'method': 'LIME'}}"]
    ArchiveOutput["{'param': {'format': 'parquet'}}"]
    ChatGPT["{'args': {'user_prompt': 'Write a short data report'}, 'param': {'model': 'gpt-4o'}}"]

    %% Multi-input ingestion
    LoadCSV -- "{'data':'csv_data'}" --> CleanData
    LoadJSON -- "{'data':'json_meta'}" --> MergeData

    CleanData -- "{'cleaned':'cleaned_data'}" --> Normalize
    Normalize -- "{'normalized':'norm_data'}" --> MergeData

    MergeData -- "{'merged_data':'data'}" --> FeatureExtract

    %% Branch to model and explainability
    FeatureExtract -- "{'features':'X'}" --> MLModel
    FeatureExtract -- "{'features':'input'}" --> ExplainModel

    %% Skip connection: CleanData directly to ExplainModel
    CleanData -- "{'cleaned':'raw_baseline'}" --> ExplainModel

    %% Outputs split
    MLModel -- "{'predictions':'y_pred'}" --> ArchiveOutput
    ExplainModel -- "{'explanation':'annotated'}" --> ChatGPT

    %% Skip: MLModel also feeds ChatGPT directly
    MLModel -- "{'probabilities':'model_insight'}" --> ChatGPT

"""
    graph = MermaidGraph(mermaid_text)
    config = graph.get_pipeline_config()

    # your registered Celery tasks
    task_registry = {
        "LoadCSV": LoadCSV,
        "LoadJSON": LoadJSON,
        "CleanData": CleanData,
        "Normalize": Normalize,
        "MergeData": MergeData,
        "FeatureExtract": FeatureExtract,
        "MLModel": MLModel,
        "ExplainModel": ExplainModel,
        "ArchiveOutput": ArchiveOutput,
        "ChatGPT": ChatGPT,
        "StoreSharedResult": StoreSharedResult,
        "LoadSharedResult": LoadSharedResult,
    }
    def pretty_signature(sig, indent=0):
        space = "  " * indent
        if hasattr(sig, "tasks"):  # group or chord
            if isinstance(sig, chord):
                print(f"{space}Chord:")
                print(f"{space}  Group:")
                for task in sig.body.tasks:
                    pretty_signature(task, indent + 2)
                print(f"{space}  Final:")
                pretty_signature(sig.body, indent + 2)
            elif isinstance(sig, group):
                print(f"{space}Group:")
                for task in sig.tasks:
                    pretty_signature(task, indent + 1)
        elif hasattr(sig, "kwargs"):
            print(f"{space}{sig.task}({sig.kwargs})")
        else:
            print(f"{space}{sig}")

    # dag = build_execution_dag(graph, task_registry, config)
    dag, steps = build_execution_dag(
        graph=graph,
        task_registry=task_registry,
        config=graph.get_pipeline_config(),
        store_task=StoreSharedResult,
        load_task=LoadSharedResult
    )

    # Print readable summary:
    for node, sig in steps.items():
        print(f"{node} → {sig!r}")

    dag.apply_async()
