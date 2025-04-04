from .Fibonacci import Fibonacci
from .PrimeNumberChecker import PrimeNumberChecker
from .PalindromeChecker import PalindromeChecker
from .ChatGPTService import ChatGPTService
from .Downloader import Downloader
from .BinaryRepresentation import BinaryRepresentation
from .CollatzSequence import CollatzSequence
from .SmartModelConverter import SmartModelConverter

SmartModelConverter.Action.ACTION_REGISTRY = {
    'Fibonacci': Fibonacci,
    'PrimeNumberChecker': PrimeNumberChecker,
    'PalindromeChecker': PalindromeChecker,
    'ChatGPTService': ChatGPTService,
    'Downloader': Downloader,
    'BinaryRepresentation': BinaryRepresentation,
    'CollatzSequence': CollatzSequence,
}
