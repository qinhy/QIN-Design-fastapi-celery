from .Fibonacci import Fibonacci
from .PrimeNumberChecker import PrimeNumberChecker
from .PalindromeChecker import PalindromeChecker
from .ChatGPTService import ChatGPTService, DeepseekService
from .Downloader import Downloader
from .BinaryRepresentation import BinaryRepresentation
from .CollatzSequence import CollatzSequence
from .UploadToFTP import UploadToFTP
from .HttpRequestTask import HttpRequestTask
from .BrowseWebLink import BrowseWebLink
from .EnhanceImage import EnhanceImage
from .AddNumbers import AddNumbers

# for advanced users
from .TaskDAGRunner import TaskDAGRunner
from .SmartModelConverter import SmartModelConverter

ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
    'PrimeNumberChecker': PrimeNumberChecker,
    'PalindromeChecker': PalindromeChecker,
    'ChatGPTService': ChatGPTService,
    'DeepseekService': DeepseekService,
    'Downloader': Downloader,
    'BinaryRepresentation': BinaryRepresentation,
    'CollatzSequence': CollatzSequence,
    'UploadToFTP': UploadToFTP,
    'HttpRequestTask': HttpRequestTask,
    'BrowseWebLink': BrowseWebLink,
    'EnhanceImage': EnhanceImage,
    'AddNumbers': AddNumbers,
}
SmartModelConverter.Action.ACTION_REGISTRY = ACTION_REGISTRY
TaskDAGRunner.Action.ACTION_REGISTRY = ACTION_REGISTRY