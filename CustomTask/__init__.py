from .Fibonacci import Fibonacci
from .PrimeNumberChecker import PrimeNumberChecker
from .PalindromeChecker import PalindromeChecker
from .ChatGPTService import ChatGPTService, DeepseekService
from .Downloader import Downloader
from .BinaryRepresentation import BinaryRepresentation
from .CollatzSequence import CollatzSequence
from .SmartModelConverter import SmartModelConverter
from .UploadToFTP import UploadToFTP

SmartModelConverter.Action.ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
    'PrimeNumberChecker': PrimeNumberChecker,
    'PalindromeChecker': PalindromeChecker,
    'ChatGPTService': ChatGPTService,
    'DeepseekService': DeepseekService,
    'Downloader': Downloader,
    'BinaryRepresentation': BinaryRepresentation,
    'CollatzSequence': CollatzSequence,
}

from .MT5Book import BookService, MT5CopyLastRatesService
from .MT5RatesDownloader import MT5RatesDownloader
