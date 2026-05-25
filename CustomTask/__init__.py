from .mini.Fibonacci import Fibonacci
from .mini.AddNumbers import AddNumbers
from .mini.AdjustImage import AdjustImage
from .mini.BinaryRepresentation import BinaryRepresentation
from .mini.BrowseWebLink import BrowseWebLink
from .mini.ChatGPTService import ChatGPTService, DeepseekService
from .mini.CollatzSequence import CollatzSequence
from .mini.Downloader import Downloader
from .mini.EnhanceImage import EnhanceImage
from .mini.FSSpecShell import FSSpecShell
from .mini.GrayscaleImage import GrayscaleImage
from .mini.HttpRequestTask import HttpRequestTask
from .mini.ImagePadding import ImagePadding
from .mini.ImageTiler import ImageTiler
from .mini.PalindromeChecker import PalindromeChecker
from .mini.PrimeNumberChecker import PrimeNumberChecker
from .mini.SimpleWebRequest import SimpleWebRequest
from .mini.UploadToFTP import UploadToFTP

# for advanced users
from .mini.TaskDAGRunner import TaskDAGRunner
from .mini.SmartModelConverter import SmartModelConverter

ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
    'AdjustImage':AdjustImage,
    'GrayscaleImage':GrayscaleImage,
    'ImagePadding':ImagePadding,
    'ImageTiler':ImageTiler,
    'SimpleWebRequest':SimpleWebRequest,
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