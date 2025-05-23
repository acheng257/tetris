# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# NO CHECKED-IN PROTOBUF GENCODE
# source: tetris.proto
# Protobuf Python Version: 5.29.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(
    _runtime_version.Domain.PUBLIC,
    5,
    29,
    0,
    '',
    'tetris.proto'
)
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0ctetris.proto\x12\x06tetris\"X\n\x0b\x41\x63tivePiece\x12\x12\n\npiece_type\x18\x01 \x01(\t\x12\t\n\x01x\x18\x02 \x01(\x05\x12\t\n\x01y\x18\x03 \x01(\x05\x12\x10\n\x08rotation\x18\x04 \x01(\x05\x12\r\n\x05\x63olor\x18\x05 \x01(\x05\"\x89\x01\n\nBoardState\x12\r\n\x05\x63\x65lls\x18\x01 \x03(\x05\x12\r\n\x05width\x18\x02 \x01(\x05\x12\x0e\n\x06height\x18\x03 \x01(\x05\x12\r\n\x05score\x18\x04 \x01(\x05\x12\x13\n\x0bplayer_name\x18\x05 \x01(\t\x12)\n\x0c\x61\x63tive_piece\x18\x06 \x01(\x0b\x32\x13.tetris.ActivePiece\"\xb9\x01\n\rTetrisMessage\x12!\n\x04type\x18\x01 \x01(\x0e\x32\x13.tetris.MessageType\x12\x0c\n\x04seed\x18\x02 \x01(\x05\x12\x0f\n\x07garbage\x18\x03 \x01(\x05\x12\x0e\n\x06sender\x18\x07 \x01(\t\x12\r\n\x05score\x18\x04 \x01(\x05\x12\x0f\n\x07results\x18\x05 \x01(\t\x12\r\n\x05\x65xtra\x18\x06 \x01(\x0c\x12\'\n\x0b\x62oard_state\x18\x08 \x01(\x0b\x32\x12.tetris.BoardState*\\\n\x0bMessageType\x12\t\n\x05READY\x10\x00\x12\t\n\x05START\x10\x01\x12\x0b\n\x07GARBAGE\x10\x02\x12\x08\n\x04LOSE\x10\x03\x12\x10\n\x0cGAME_RESULTS\x10\x04\x12\x0e\n\nGAME_STATE\x10\x05\x32K\n\rTetrisService\x12:\n\x04Play\x12\x15.tetris.TetrisMessage\x1a\x15.tetris.TetrisMessage\"\x00(\x01\x30\x01\x62\x06proto3')

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'tetris_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
  DESCRIPTOR._loaded_options = None
  _globals['_MESSAGETYPE']._serialized_start=442
  _globals['_MESSAGETYPE']._serialized_end=534
  _globals['_ACTIVEPIECE']._serialized_start=24
  _globals['_ACTIVEPIECE']._serialized_end=112
  _globals['_BOARDSTATE']._serialized_start=115
  _globals['_BOARDSTATE']._serialized_end=252
  _globals['_TETRISMESSAGE']._serialized_start=255
  _globals['_TETRISMESSAGE']._serialized_end=440
  _globals['_TETRISSERVICE']._serialized_start=536
  _globals['_TETRISSERVICE']._serialized_end=611
# @@protoc_insertion_point(module_scope)
