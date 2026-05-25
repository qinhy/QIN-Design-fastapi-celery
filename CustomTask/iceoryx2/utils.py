from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

import iceoryx2 as iox2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

# Image dtype ids. Keep this stable once data is in production.
DTYPE_UINT8 = 1

IMAGE_MAGIC = 0x494D4731  # "IMG1"
IMAGE_VERSION = 1
IMAGE_FLAG_CHANNEL_DIM = 1 << 0  # The original NumPy image had an explicit C dimension.

HEALTH_MAGIC = 0x48544C48  # "HLTH"
HEALTH_VERSION = 1

STATUS_OK = 0
STATUS_WARN = 1
STATUS_ERROR = 2

UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF


def _ptr_to_int(ptr: Any) -> int:
    """Normalize pointer-like values returned by the iceoryx2 FFI."""
    if isinstance(ptr, int):
        value = ptr
    elif isinstance(ptr, ctypes.c_void_p):
        if ptr.value is None:
            raise ValueError("null pointer")
        value = int(ptr.value)
    else:
        try:
            value = int(ptr)
        except Exception as exc:  # pragma: no cover - defensive for FFI changes
            raise TypeError(f"unsupported pointer type: {type(ptr)!r}") from exc

    if value == 0:
        raise ValueError("null pointer")
    return value


def slice_len(slice_obj: Any) -> int:
    """Return the byte length of an iceoryx2 slice."""
    return int(slice_obj.len())


def slice_ptr(slice_obj: Any) -> int:
    """Return the base address of an iceoryx2 slice as an integer."""
    return _ptr_to_int(slice_obj.as_ptr())


def _validate_size_and_shape(size: int, shape: Iterable[int] | None) -> tuple[int, ...] | None:
    if size < 0:
        raise ValueError(f"size must be non-negative, got {size}")
    if shape is None:
        return None

    normalized = tuple(int(dim) for dim in shape)
    if any(dim < 0 for dim in normalized):
        raise ValueError(f"shape dimensions must be non-negative, got {normalized}")

    expected = int(np.prod(normalized, dtype=np.int64)) if normalized else 1
    if expected != size:
        raise ValueError(f"shape {normalized} requires {expected} bytes, got {size}")
    return normalized


def u8_slice_to_numpy(
    slice_obj: Any,
    shape: Iterable[int] | None = None,
    *,
    writable: bool = True,
) -> np.ndarray:
    """Create a NumPy uint8 view over an ``iox2.Slice[ctypes.c_uint8]``.

    The returned array is zero-copy. On the subscriber side it is valid only
    while the iceoryx2 sample object is alive.
    """
    n = slice_len(slice_obj)
    ptr = slice_ptr(slice_obj)
    return u8_address_to_numpy(ptr, n, shape=shape, writable=writable)


def u8_address_to_numpy(
    address: int,
    size: int,
    shape: Iterable[int] | None = None,
    *,
    writable: bool = True,
) -> np.ndarray:
    """Create a NumPy uint8 view from an address and byte size."""
    size = int(size)
    normalized_shape = _validate_size_and_shape(size, shape)
    address = _ptr_to_int(address)

    c_array_type = ctypes.c_uint8 * size
    c_array = c_array_type.from_address(address)
    arr = np.ctypeslib.as_array(c_array)

    if normalized_shape is not None:
        arr = arr.reshape(normalized_shape)

    if not writable:
        arr.setflags(write=False)

    return arr


def _packed_payload_size(width: int, height: int, channels: int) -> int:
    return int(width) * int(height) * int(channels)


def _image_channels(image: np.ndarray) -> int:
    return int(image.shape[2]) if image.ndim == 3 else 1


class ImageHeader(ctypes.Structure):
    """Header placed before image bytes in an iceoryx2 uint8 slice.

    The payload layout is packed uint8 pixels. Grayscale images may be sent as
    either HxW or HxWx1; ``flags`` records whether the channel dimension was
    explicit on the publishing side.
    """

    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint16),
        ("header_size", ctypes.c_uint16),
        ("frame_id", ctypes.c_uint64),
        ("timestamp_ns", ctypes.c_uint64),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("channels", ctypes.c_uint16),
        ("dtype", ctypes.c_uint16),
        ("stride_bytes", ctypes.c_uint32),
        ("payload_size", ctypes.c_uint64),
        ("source_id", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint64),
        ("reserved1", ctypes.c_uint64),
    ]

    @staticmethod
    def type_name() -> str:
        return "ioxbus.ImageHeader.v1"

    @staticmethod
    def make_header(image: np.ndarray, timestamp_ns: int | None = None) -> ImageHeader:
        if image.dtype != np.uint8:
            raise TypeError(f"expected uint8 image, got {image.dtype}")
        if image.ndim not in (2, 3):
            raise ValueError(f"expected HxW or HxWxC image, got shape={image.shape}")

        height = int(image.shape[0])
        width = int(image.shape[1])
        channels = _image_channels(image)

        header = ImageHeader()
        header.magic = IMAGE_MAGIC
        header.version = IMAGE_VERSION
        header.header_size = IMAGE_HEADER_SIZE
        header.frame_id = 0
        header.timestamp_ns = int(time.time_ns() if timestamp_ns is None else timestamp_ns)
        header.width = width
        header.height = height
        header.channels = channels
        header.dtype = DTYPE_UINT8
        header.stride_bytes = int(image.strides[0])
        header.payload_size = int(image.nbytes)
        header.source_id = 0
        header.flags = IMAGE_FLAG_CHANNEL_DIM if image.ndim == 3 else 0
        header.reserved0 = 0
        header.reserved1 = 0
        return header


IMAGE_HEADER_SIZE = ctypes.sizeof(ImageHeader)


class ServiceHealth(ctypes.Structure):
    """Small fixed-layout monitoring message for optional iceoryx2 health topics."""

    _fields_ = [
        ("magic", ctypes.c_uint32),
        ("version", ctypes.c_uint16),
        ("status", ctypes.c_uint16),
        ("pid", ctypes.c_uint32),
        ("service_id", ctypes.c_uint32),
        ("time_ns", ctypes.c_uint64),
        ("uptime_ms", ctypes.c_uint64),
        ("frame_id", ctypes.c_uint64),
        ("published_frames", ctypes.c_uint64),
        ("received_frames", ctypes.c_uint64),
        ("dropped_frames", ctypes.c_uint64),
        ("error_count", ctypes.c_uint64),
        ("fps_x1000", ctypes.c_uint32),
        ("copy_us", ctypes.c_uint32),
        ("latency_us", ctypes.c_uint32),
        ("cpu_x1000", ctypes.c_uint32),
        ("rss_bytes", ctypes.c_uint64),
        ("last_error_code", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    ]

    @staticmethod
    def type_name() -> str:
        return "ioxbus.ServiceHealth.v1"


@dataclass(frozen=True)
class ImageFrame:
    """Received image frame.

    Keep this object alive while using ``image``. It owns the iceoryx2 sample
    whose shared-memory lifetime backs the NumPy view.
    """

    header: ImageHeader
    image: np.ndarray
    sample: Any

    @property
    def latency_us(self) -> int:
        if int(self.header.timestamp_ns) == 0:
            return 0
        return max(0, (time.time_ns() - int(self.header.timestamp_ns)) // 1000)


class RateMeter:
    def __init__(self, window_s: float = 1.0):
        if window_s <= 0:
            raise ValueError(f"window_s must be positive, got {window_s}")
        self.window_s = float(window_s)
        self.last_t = time.perf_counter()
        self.count = 0
        self.value = 0.0

    def tick(self, n: int = 1) -> float:
        self.count += int(n)
        now = time.perf_counter()
        dt = now - self.last_t

        if dt >= self.window_s:
            self.value = self.count / dt
            self.count = 0
            self.last_t = now

        return self.value


def _validate_header(header: ImageHeader) -> None:
    if int(header.magic) != IMAGE_MAGIC:
        raise ValueError(f"bad image magic: {int(header.magic):#x}")
    if int(header.version) != IMAGE_VERSION:
        raise ValueError(f"unsupported image version: {int(header.version)}")
    if int(header.header_size) != IMAGE_HEADER_SIZE:
        raise ValueError(f"bad header size: {int(header.header_size)}")
    if int(header.dtype) != DTYPE_UINT8:
        raise ValueError(f"unsupported dtype id: {int(header.dtype)}")
    if int(header.width) <= 0 or int(header.height) <= 0 or int(header.channels) <= 0:
        raise ValueError(
            "invalid image dimensions: "
            f"width={int(header.width)}, height={int(header.height)}, channels={int(header.channels)}"
        )

    expected_payload = _packed_payload_size(header.width, header.height, header.channels)
    if int(header.payload_size) != expected_payload:
        raise ValueError(
            f"unexpected payload size: got={int(header.payload_size)}, expected={expected_payload}"
        )


def _shape_from_header(header: ImageHeader) -> tuple[int, ...]:
    height = int(header.height)
    width = int(header.width)
    channels = int(header.channels)

    if channels == 1 and not (int(header.flags) & IMAGE_FLAG_CHANNEL_DIM):
        return (height, width)
    return (height, width, channels)


class IoxImagePublisher(BaseModel):
    """Publish NumPy uint8 images as ``[ImageHeader][packed bytes]`` via iceoryx2."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", validate_assignment=True)

    topic: str = Field(..., description="Topic name, for example /your/topic/name")
    width: int = Field(..., gt=0, le=UINT32_MAX, description="Image width")
    height: int = Field(..., gt=0, le=UINT32_MAX, description="Image height")
    channels: int = Field(..., gt=0, le=0xFFFF, description="Number of image channels")
    source_id: int = Field(..., ge=0, le=UINT32_MAX, description="Source ID")
    frame_id: int = Field(default=0, ge=0, le=UINT64_MAX, description="Last published frame ID")
    payload_bytes: int = Field(default=0, ge=0, description="Computed packed payload size in bytes")
    total_bytes: int = Field(default=0, ge=0, description="Computed total slice size in bytes")
    max_payload_bytes: int = Field(
        default=0,
        ge=0,
        description="Maximum total slice bytes, including header; 0 means configured frame size",
    )

    _node: Any = PrivateAttr(default=None)
    _publisher: Any = PrivateAttr(default=None)
    _frame_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @field_validator("topic")
    @classmethod
    def _topic_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic must not be empty")
        return value

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)

        self.payload_bytes = _packed_payload_size(self.width, self.height, self.channels)
        self.total_bytes = IMAGE_HEADER_SIZE + self.payload_bytes
        self.max_payload_bytes = int(self.max_payload_bytes or self.total_bytes)
        if self.max_payload_bytes < self.total_bytes:
            raise ValueError(
                f"max_payload_bytes={self.max_payload_bytes} is smaller than configured "
                f"frame size total_bytes={self.total_bytes}"
            )

        self._node = iox2.NodeBuilder.new().create(iox2.ServiceType.Ipc)
        service = (
            self._node.service_builder(iox2.ServiceName.new(self.topic))
            .publish_subscribe(iox2.Slice[ctypes.c_uint8])
            .open_or_create()
        )
        self._publisher = (
            service.publisher_builder()
            .initial_max_slice_len(self.max_payload_bytes)
            .allocation_strategy(iox2.AllocationStrategy.Static)
            .create()
        )

    @property
    def publisher(self) -> Any:
        if self._publisher is None:
            raise RuntimeError("publisher is not initialized")
        return self._publisher

    def _validate_image_shape(self, image: np.ndarray) -> None:
        if image.ndim not in (2, 3):
            raise ValueError(f"expected HxW or HxWxC image, got shape={image.shape}")

        height = int(image.shape[0])
        width = int(image.shape[1])
        channels = _image_channels(image)
        expected = (self.height, self.width, self.channels)
        actual = (height, width, channels)
        if actual != expected:
            raise ValueError(f"image shape mismatch: got HWC={actual}, expected HWC={expected}")

    def make_header(self, image: np.ndarray, timestamp_ns: int | None = None) -> ImageHeader:
        header = ImageHeader.make_header(image, timestamp_ns)
        with self._frame_lock:
            self.frame_id += 1
            header.frame_id = self.frame_id
        header.source_id = self.source_id
        return header

    def publish(self, image: np.ndarray, *, timestamp_ns: int | None = None) -> dict[str, int]:
        if not isinstance(image, np.ndarray):
            raise TypeError(f"expected numpy.ndarray, got {type(image)!r}")
        if image.dtype != np.uint8:
            raise TypeError(f"expected uint8 image, got {image.dtype}")
        self._validate_image_shape(image)

        image = np.ascontiguousarray(image)
        header = self.make_header(image, timestamp_ns=timestamp_ns)
        _validate_header(header)

        total_bytes = IMAGE_HEADER_SIZE + int(header.payload_size)
        if total_bytes > self.max_payload_bytes:
            raise ValueError(
                f"image too large for publisher allocation: total={total_bytes}, "
                f"max={self.max_payload_bytes}"
            )

        sample = self.publisher.loan_slice_uninit(total_bytes)
        payload = sample.payload()
        if slice_len(payload) < total_bytes:
            raise RuntimeError(f"loaned slice too small: got={slice_len(payload)}, expected={total_bytes}")

        base_addr = slice_ptr(payload)

        copy_t0 = time.perf_counter_ns()
        ctypes.memmove(base_addr, ctypes.byref(header), IMAGE_HEADER_SIZE)
        ctypes.memmove(base_addr + IMAGE_HEADER_SIZE, image.ctypes.data, int(header.payload_size))
        copy_t1 = time.perf_counter_ns()

        sample = sample.assume_init()
        sample.send()

        frame_id=int(header.frame_id)
        timestamp_ns=int(header.timestamp_ns)
        payload_size=int(header.payload_size)
        copy_us=int((copy_t1 - copy_t0) // 1000)
        return frame_id,timestamp_ns,payload_size,copy_us

class IoxImageSubscriber(BaseModel):
    """Receive image frames and expose a zero-copy NumPy view."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    topic: str = Field(..., description="Topic name, for example /your/topic/name")

    _node: Any = PrivateAttr(default=None)
    _subscriber: Any = PrivateAttr(default=None)

    @field_validator("topic")
    @classmethod
    def _topic_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("topic must not be empty")
        return value

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)

        self._node = iox2.NodeBuilder.new().create(iox2.ServiceType.Ipc)
        service = (
            self._node.service_builder(iox2.ServiceName.new(self.topic))
            .publish_subscribe(iox2.Slice[ctypes.c_uint8])
            .open_or_create()
        )
        self._subscriber = service.subscriber_builder().create()

    @property
    def subscriber(self) -> Any:
        if self._subscriber is None:
            raise RuntimeError("subscriber is not initialized")
        return self._subscriber

    def receive(self) -> ImageFrame | None:
        sample = self.subscriber.receive()
        if sample is None:
            return None

        payload = sample.payload()
        payload_len = slice_len(payload)
        if payload_len < IMAGE_HEADER_SIZE:
            raise ValueError(f"payload too small: {payload_len}")

        base_addr = slice_ptr(payload)
        header = ImageHeader.from_buffer_copy(ctypes.string_at(base_addr, IMAGE_HEADER_SIZE))
        _validate_header(header)

        expected = IMAGE_HEADER_SIZE + int(header.payload_size)
        if payload_len < expected:
            raise ValueError(f"payload truncated: got={payload_len}, expected={expected}")

        image = u8_address_to_numpy(
            base_addr + IMAGE_HEADER_SIZE,
            int(header.payload_size),
            shape=_shape_from_header(header),
            writable=False,
        )

        return ImageFrame(header=header, image=image, sample=sample)
