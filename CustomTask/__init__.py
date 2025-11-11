
from .AddNumbers import AddNumbers
from .AdjustImage import AdjustImage
from .BinaryRepresentation import BinaryRepresentation
from .BrowseWebLink import BrowseWebLink
from .ChatGPTService import ChatGPTService, DeepseekService
from .CollatzSequence import CollatzSequence
from .Downloader import Downloader
from .EnhanceImage import EnhanceImage
from .Fibonacci import Fibonacci
from .FSSpecShell import FSSpecShell
from .GrayscaleImage import GrayscaleImage
from .HttpRequestTask import HttpRequestTask
from .ImagePadding import ImagePadding
from .ImageTiler import ImageTiler
from .PalindromeChecker import PalindromeChecker
from .PrimeNumberChecker import PrimeNumberChecker
from .SimpleWebRequest import SimpleWebRequest
from .UploadToFTP import UploadToFTP

# for advanced users
from .TaskDAGRunner import TaskDAGRunner
from .SmartModelConverter import SmartModelConverter

ACTION_REGISTRY = {
    'AdjustImage':AdjustImage,
    'GrayscaleImage':GrayscaleImage,
    'ImagePadding':ImagePadding,
    'ImageTiler':ImageTiler,
    'SimpleWebRequest':SimpleWebRequest,
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
    'FSSpecShell': FSSpecShell,
}
SmartModelConverter.Action.ACTION_REGISTRY = ACTION_REGISTRY
TaskDAGRunner.Action.ACTION_REGISTRY = ACTION_REGISTRY