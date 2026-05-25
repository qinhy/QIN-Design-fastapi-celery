from .mini.Fibonacci import Fibonacci
# from .AddNumbers import AddNumbers
# from .AdjustImage import AdjustImage
# from .BinaryRepresentation import BinaryRepresentation
# from .BrowseWebLink import BrowseWebLink
# from .ChatGPTService import ChatGPTService, DeepseekService
# from .CollatzSequence import CollatzSequence
# from .Downloader import Downloader
# from .EnhanceImage import EnhanceImage
# from .FSSpecShell import FSSpecShell
# from .GrayscaleImage import GrayscaleImage
# from .HttpRequestTask import HttpRequestTask
# from .ImagePadding import ImagePadding
# from .ImageTiler import ImageTiler
# from .PalindromeChecker import PalindromeChecker
# from .PrimeNumberChecker import PrimeNumberChecker
# from .SimpleWebRequest import SimpleWebRequest
# from .UploadToFTP import UploadToFTP
from .iceoryx2.NumpyImageSteam import NumpyImageSteam

# for advanced users
from .mini.TaskDAGRunner import TaskDAGRunner
from .mini.SmartModelConverter import SmartModelConverter

ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
    # 'AdjustImage':AdjustImage,
    # 'GrayscaleImage':GrayscaleImage,
    # 'ImagePadding':ImagePadding,
    # 'ImageTiler':ImageTiler,
    # 'SimpleWebRequest':SimpleWebRequest,
    # 'PrimeNumberChecker': PrimeNumberChecker,
    # 'PalindromeChecker': PalindromeChecker,
    # 'ChatGPTService': ChatGPTService,
    # 'DeepseekService': DeepseekService,
    # 'Downloader': Downloader,
    # 'BinaryRepresentation': BinaryRepresentation,
    # 'CollatzSequence': CollatzSequence,
    # 'UploadToFTP': UploadToFTP,
    # 'HttpRequestTask': HttpRequestTask,
    # 'BrowseWebLink': BrowseWebLink,
    # 'EnhanceImage': EnhanceImage,
    # 'AddNumbers': AddNumbers,
    # 'FSSpecShell': FSSpecShell,
    'NumpyImageSteam': NumpyImageSteam,
}
SmartModelConverter.Action.ACTION_REGISTRY = ACTION_REGISTRY
TaskDAGRunner.Action.ACTION_REGISTRY = ACTION_REGISTRY