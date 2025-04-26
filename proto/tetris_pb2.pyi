from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MessageType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    READY: _ClassVar[MessageType]
    START: _ClassVar[MessageType]
    GARBAGE: _ClassVar[MessageType]
    LOSE: _ClassVar[MessageType]
    GAME_RESULTS: _ClassVar[MessageType]
    GAME_STATE: _ClassVar[MessageType]
READY: MessageType
START: MessageType
GARBAGE: MessageType
LOSE: MessageType
GAME_RESULTS: MessageType
GAME_STATE: MessageType

class ActivePiece(_message.Message):
    __slots__ = ("piece_type", "x", "y", "rotation", "color")
    PIECE_TYPE_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    ROTATION_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    piece_type: str
    x: int
    y: int
    rotation: int
    color: int
    def __init__(self, piece_type: _Optional[str] = ..., x: _Optional[int] = ..., y: _Optional[int] = ..., rotation: _Optional[int] = ..., color: _Optional[int] = ...) -> None: ...

class BoardState(_message.Message):
    __slots__ = ("cells", "width", "height", "score", "player_name", "active_piece")
    CELLS_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_NAME_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_PIECE_FIELD_NUMBER: _ClassVar[int]
    cells: _containers.RepeatedScalarFieldContainer[int]
    width: int
    height: int
    score: int
    player_name: str
    active_piece: ActivePiece
    def __init__(self, cells: _Optional[_Iterable[int]] = ..., width: _Optional[int] = ..., height: _Optional[int] = ..., score: _Optional[int] = ..., player_name: _Optional[str] = ..., active_piece: _Optional[_Union[ActivePiece, _Mapping]] = ...) -> None: ...

class TetrisMessage(_message.Message):
    __slots__ = ("type", "seed", "garbage", "sender", "score", "results", "extra", "board_state")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    GARBAGE_FIELD_NUMBER: _ClassVar[int]
    SENDER_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    BOARD_STATE_FIELD_NUMBER: _ClassVar[int]
    type: MessageType
    seed: int
    garbage: int
    sender: str
    score: int
    results: str
    extra: bytes
    board_state: BoardState
    def __init__(self, type: _Optional[_Union[MessageType, str]] = ..., seed: _Optional[int] = ..., garbage: _Optional[int] = ..., sender: _Optional[str] = ..., score: _Optional[int] = ..., results: _Optional[str] = ..., extra: _Optional[bytes] = ..., board_state: _Optional[_Union[BoardState, _Mapping]] = ...) -> None: ...
