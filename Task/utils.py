import re
import json
from collections import defaultdict, deque
from typing import Any, Dict, List

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

        
if __name__ == "__main__":
    import json
    c_test = """
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
    # print(json.dumps(MermaidGraph(c_test).graph, indent=2))
    print(MermaidGraph(c_test).get_pipeline_order())
    # print(MermaidGraph(c_test).get_pipeline_config())
    # print(MermaidGraph(c_test).get_pipeline_services(["Fibonacci", "PrimeNumberChecker", "BinaryRepresentation", "ChatGPTService"]))
    print(MermaidGraph(c_test).get_pipeline_mappings())