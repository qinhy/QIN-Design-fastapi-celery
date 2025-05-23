import base64
import json
import os
import re
import tempfile
from collections import defaultdict, deque
from typing import Any, Dict, List
import fsspec
import requests
import os
import fsspec
from typing import Tuple, Optional

try:
    from .rjson import load_RSAs
except:
    from rjson import load_RSAs

class FileInputHelper:
    """Helper class for handling file system operations."""    
    @staticmethod
    def read_rjson(content: str) -> dict:
        try:
            return load_RSAs(content,os.getenv("RSA_PRIVATE_KEY"))
        except:
            return None

    def get_fsspec_from_env_and_path(path: Optional[str] = None) -> Tuple[fsspec.AbstractFileSystem, str]:
        """
        Load FILE_SYSTEM configuration from environment and build filesystem + full path.
        Supports S3, FTP, or fallback to local.
        """
        # Default fallback to local file system
        fs_type = os.getenv("FILE_SYSTEM_TYPE", "file")
        base_path = os.getenv("FILE_SYSTEM_BASE_PATH", "./")
        fs = fsspec.filesystem(fs_type)
        full_path = os.path.join(base_path, path or "")

        data = FileInputHelper.read_rjson(os.getenv("FILE_SYSTEM"))
        if data is not None:
            fs_type = data.get("type", "").lower()
            
            if fs_type == "s3":
                # {
                # "type": "s3",
                # "bucket": "my-sample-bucket",
                # "key": "data/sample.txt",
                # "aws_access_key_id": "YOUR_AWS_ACCESS_KEY_ID",
                # "aws_secret_access_key": "YOUR_AWS_SECRET_ACCESS_KEY",
                # "aws_session_token": "YOUR_AWS_SESSION_TOKEN",  // optional
                # "region": "us-west-2"  // optional
                # }
                bucket = data.get("bucket")
                key = data.get("key") or path
                aws_key = data.get("aws_access_key_id")
                aws_secret = data.get("aws_secret_access_key")
                aws_token = data.get("aws_session_token", None)
                region = data.get("region", None)

                fs_kwargs = {
                    "key": aws_key,
                    "secret": aws_secret,
                }
                if aws_token:
                    fs_kwargs["token"] = aws_token
                if region:
                    fs_kwargs["client_kwargs"] = {"region_name": region}

                fs = fsspec.filesystem("s3", **fs_kwargs)
                full_path = f"s3://{bucket}/{key.lstrip('/')}"
                return fs, full_path

            elif fs_type == "ftp":
                # {
                # "type": "ftp",
                # "host": "ftp.example.com",
                # "path": "/files/data.txt",
                # "port": 21,
                # "username": "user",          // optional
                # "password": "secret"         // optional
                # }
                host = data.get("host")
                remote_path = data.get("path") or path
                port = data.get("port", 21)
                username = data.get("username", None)
                password = data.get("password", None)

                fs_kwargs = {"host": host, "port": port}
                if username:
                    fs_kwargs["username"] = username
                if password:
                    fs_kwargs["password"] = password

                fs = fsspec.filesystem("ftp", **fs_kwargs)
                full_path = f"ftp://{host}/{remote_path.lstrip('/')}"
                return fs, full_path

        return fs, full_path

    @staticmethod
    def open(filename: str, mode: str = "r") -> fsspec.core.OpenFile:
        fs, full_path = FileInputHelper.get_fsspec_from_env_and_path(filename)
        return fs.open(full_path, mode)
    
    @staticmethod
    def resolve_to_local_path(source: str, default_ext: str = ".bin") -> str:
        """
        Resolves a source (file path, URL, or base64) to a temporary local file path.
        """
        if FileInputHelper.is_url(source):
            return FileInputHelper._download_to_temp_file(source, default_ext)
        elif FileInputHelper.is_base64(source):
            return FileInputHelper._decode_base64_to_temp_file(source, default_ext)
        elif os.path.exists(source):
            return source
        else:
            raise ValueError("Unsupported file source: must be a path, URL, or base64 string.")

    @staticmethod
    def is_url(source: str) -> bool:
        return source.startswith("http://") or source.startswith("https://")

    @staticmethod
    def is_base64(source: str) -> bool:
        return bool(re.match(r"^data:[^;]+;base64,", source))

    @staticmethod
    def _download_to_temp_file(url: str, default_ext: str) -> str:
        response = requests.get(url)
        if not response.ok:
            raise ValueError(f"Failed to download from URL: {url}")
        ext = os.path.splitext(url)[-1] or default_ext
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(response.content)
            return tmp.name

    @staticmethod
    def _decode_base64_to_temp_file(data_uri: str, default_ext: str) -> str:
        header, encoded = data_uri.split(',', 1)
        mime = header.split(':')[1].split(';')[0]
        ext = FileInputHelper._mime_to_ext(mime) or default_ext
        data = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(data)
            return tmp.name

    @staticmethod
    def _mime_to_ext(mime: str) -> str:
        return {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'application/pdf': '.pdf',
            'text/plain': '.txt',
        }.get(mime, '.bin')

    @staticmethod
    def delete_temp_file(path: str):
        """Delete the specified temporary file if it exists."""
        try:
            if os.path.exists(path) and FileInputHelper._is_in_temp_dir(path):
                os.remove(path)
        except Exception as e:
            # Silently ignore or optionally log
            print(f"[Warning] Could not delete temp file {path}: {e}")

    @staticmethod
    def _is_in_temp_dir(path: str) -> bool:
        # Only allow deletion if file resides in temp directory
        return os.path.commonpath([path, tempfile.gettempdir()]) == tempfile.gettempdir()

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
    g = MermaidGraph(
        MermaidGraph.TEST_GRAPH
    )
    print(g.get_pipeline_config())
    print(g.get_pipeline_mappings())