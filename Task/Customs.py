import time
from pydantic import BaseModel
from .Basic import CommonStreamIO, ServiceOrientedArchitecture

class Fibonacci(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            mode: str = 'fast'
            def is_fast(self):
                return self.mode=='fast'
        class Args(BaseModel):
            n: int = 1
        class Return(BaseModel):
            n: int = -1

        param:Param = Param()
        args:Args
        ret:Return = Return()

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model):
            # Ensure model is a Fibonacci instance, even if a dict is passed
            if isinstance(model, dict):
                model = Fibonacci.Model(**model)            
            self.model: Fibonacci.Model = model

        def __call__(self, *args, **kwargs):
            with self.listen_stop_flag() as stop_flag:
                n = self.model.args.n
                if n <= 1:
                    self.model.ret.n = n
                else:
                    if self.model.param.is_fast():
                        a, b = 0, 1
                        for _ in range(2, n + 1):
                            if stop_flag.is_set():
                                break
                            a, b = b, a + b
                        res = b
                    else:
                        def fib_r(n):
                            if stop_flag.is_set(): return 0
                            if n<1:return n
                            return(fib_r(n-1) + fib_r(n-2))                    
                        res = fib_r(n)
                    self.model.ret.n = res
                        
                if stop_flag.is_set():
                    self.model.ret.n = 0
                
                return self.model
            
class BidirectionalStreamService(ServiceOrientedArchitecture):
    class Model(ServiceOrientedArchitecture.Model):
        
        class Param(BaseModel):
            stream_reader:CommonStreamIO.StreamReader=None
            stream_writer:CommonStreamIO.StreamWriter=None
        class Args(BaseModel):
            pass
        class Return(BaseModel):
            pass

        # id: str= Field(default_factory=lambda:f"BidirectionalStream.Bidirectionalf:{uuid4()}")
        param:Param = Param()
        args:Args = Args()
        ret:Return = Return()

    class Action(ServiceOrientedArchitecture.Action):
        def __init__(self, model, frame_processor=lambda i,frame,frame_metadata:(frame,frame_metadata)):
            if isinstance(model, dict):
                model = BidirectionalStreamService.Bidirectional.Model(**model)
            self.model: BidirectionalStreamService.Bidirectional.Model = model
            self.frame_processor = frame_processor
            
        def __call__(self, *args, **kwargs):
            stream_reader:CommonStreamIO.StreamReader = self.model.param.stream_reader
            stream_writer:CommonStreamIO.StreamWriter = self.model.param.stream_writer
            if stream_reader is None:raise ValueError('stream_reader is None')
            if stream_writer is None:raise ValueError('stream_writer is None')
            with self.listen_stop_flag() as stop_flag:      
                res = {'msg':''}
                try:
                    for frame_count,(image,frame_metadata) in enumerate(stream_reader):
                        if stop_flag.is_set(): break
                        if frame_count%100==0:
                            start_time = time.time()
                        else:
                            elapsed_time = time.time() - start_time + 1e-5
                            frame_metadata['fps'] = fps = (frame_count%100) / elapsed_time
                            
                        image,frame_processor_metadata = self.frame_processor(frame_count,image,frame_metadata)
                        frame_metadata.update(frame_processor_metadata)
                        stream_writer.write(image,frame_metadata)

                        if frame_count%1000==100:
                            metadata = stream_writer.get_steam_info()
                            metadata['fps'] = fps
                            stream_writer.set_steam_info(metadata)

                except Exception as e:
                        res['error'] = str(e)
                        print(res)
                finally:
                    stream_reader.close()
                    stream_writer.close()
                    return res
                