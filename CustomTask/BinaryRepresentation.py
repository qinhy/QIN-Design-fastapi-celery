import threading
from typing import Optional, List
from pydantic import BaseModel, Field
try:
    from Task.Basic import ServiceOrientedArchitecture
except:
    from MockServiceOrientedArchitecture import ServiceOrientedArchitecture

class BinaryRepresentation(ServiceOrientedArchitecture):
    @classmethod
    def description(cls):
        return """
Converts an integer to its binary representation.
Supports optional bit length specification for padding with leading zeros.
Returns the binary representation as a list of bits.
"""
    
    class Levels(ServiceOrientedArchitecture.Model.Logger.Levels):
        pass

    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            bit_length: Optional[int] = Field(
                None, description="Optional bit length for output (pads with leading zeros if set)"
            )

        class Args(BaseModel):
            n: int = Field(0, description="The integer to convert to binary")

        class Return(BaseModel):
            binary: List[int] = Field(default_factory=list, description="The binary representation as a list of bits")

        
        class Logger(ServiceOrientedArchitecture.Model.Logger):
            pass
        class Version(ServiceOrientedArchitecture.Model.Version):
            pass        

        @staticmethod
        def examples():
            return [{
                "param": {"bit_length": 8},
                "args": {"n": 13}
            }]

        version:Version = Version()
        param: Param = Param()
        args: Args = Args()
        ret: Optional[Return] = Return()
        logger: Logger = Logger(name=Version().class_name)

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, BasicApp, level=None):
            super().__init__(model, BasicApp, level)
            self.model: BinaryRepresentation.Model = self.model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                if stop_flag.is_set():
                    return self.to_stop()

                n = self.model.args.n
                bit_length = self.model.param.bit_length
                self.log_and_send(f"Converting {n} to binary with bit_length={bit_length}")

                binary_bits = list(map(int, bin(n)[2:]))  # Remove '0b' prefix

                if bit_length is not None:
                    padding = max(0, bit_length - len(binary_bits))
                    binary_bits = [0] * padding + binary_bits

                self.model.ret.binary = binary_bits
                self.log_and_send(f"Binary representation: {binary_bits}")
                return self.model

        def to_stop(self):
            self.log_and_send("Stop flag detected. Returning empty result.", BinaryRepresentation.Levels.WARNING)
            self.model.ret.binary = []
            return self.model

        def log_and_send(self, message, level=None):
            if level is None:
                level = self.logger.level
            self.logger.log(level, message)
            self.send_data_to_task({level: message})


# Simple test code for the BinaryRepresentation class
if __name__ == "__main__":
    # Create a model instance
    model = BinaryRepresentation.Model()
    
    # Configure the model
    model.args.n = 13
    model.param.bit_length = 8
    
    action = BinaryRepresentation.Action(model, None)
    
    # Execute the conversion
    print("Starting binary conversion test...")
    result = action()
    
    # Print the result
    print(f"Binary representation: {result.ret.binary}")
    
    # Test with a different number
    print("\nTesting with a different number...")
    model.args.n = 42
    result = action()
    print(f"Binary representation for 42: {result.ret.binary}")
    
    # Test without bit length padding
    print("\nTesting without bit length padding...")
    model.args.n = 255
    model.param.bit_length = None
    result = action()
    print(f"Binary representation for 255 (no padding): {result.ret.binary}")
