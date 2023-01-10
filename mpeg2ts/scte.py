#!/usr/bin/env python3

from util.bitstream import BitStream
from mpeg2ts.section import Section

class SpliceInfoSection(Section):
  def __init__(self, payload=b''):
    super().__init__(payload)
    bitstream = BitStream(payload[Section.BASIC_HEADER_SIZE:])
    self.protocol_version = bitstream.readBits(8)
    self.encrypted_packet = bitstream.readBool()
    self.encryption_algorithm = bitstream.readBits(6)
    self.pts_adjustment = bitstream.readBits(33)
    self.cw_index = bitstream.readBits(8)
    self.tier = bitstream.readBits(12)
    self.splice_command_length = bitstream.readBits(12)
    self.splice_command_type = bitstream.readBits(8)
    if self.splice_command_type == 0x00:
      self.splice_command = SpliceNull(bitstream)
    elif self.splice_command_type == 0x04:
      self.splice_command = SpliceSchedule(bitstream)
    elif self.splice_command_type == 0x05:
      self.splice_command = SpliceInsert(bitstream)
    elif self.splice_command_type == 0x06:
      self.splice_command = TimeSignal(bitstream)
    elif self.splice_command_type == 0x07:
      self.splice_command = BandwidthReservation(bitstream)
    elif self.splice_command_type == 0xff:
      self.splice_command = PrivateCommand(bitstream, self.splice_command_length)
    self.descriptor_loop_length = bitstream.readBits(16)
    descriptor_stream = bitstream.readBitStreamFromBytes(self.descriptor_loop_length)
    self.descriptors = []
    while descriptor_stream:
      descriptor_tag = descriptor_stream.readBits(8)
      descriptor_stream.retainByte(descriptor_tag)
      if descriptor_tag == 0x00:
        self.descriptors.append(AvailDescriptor(descriptor_stream))
      elif descriptor_tag == 0x01:
        self.descriptors.append(DTMFDescriptor(descriptor_stream))
      elif descriptor_tag == 0x02:
        self.descriptors.append(SegmentationDescriptor(descriptor_stream))
      elif descriptor_tag == 0x03:
        self.descriptors.append(TimeDescriptor(descriptor_stream))
      elif descriptor_tag == 0x04:
        self.descriptors.append(AudioDescriptor(descriptor_tag))

    if self.encrypted_packet:
      self.E_CRC_32 = bitstream.readBits(32)

class SpliceNull:
  def __init__(self, bitstream):
    pass

class SpliceSchedule:
  def __init__(self, bitstream):
    self.splice_count = bitstream.readBits(8)
    self.events = [
      SpliceScheduleEvent(bitstream)
      for _ in range(self.splice_count)
    ]

class SpliceScheduleEvent:
  def __init__(self, bitstream):
    self.splice_event_id = bitstream.readBits(32)
    self.splice_event_cancel_indicator = bitstream.readBool()
    bitstream.readBits(7)
    if not self.splice_event_cancel_indicator:
      self.out_of_network_indicator = bitstream.readBool()
      self.program_splice_flag = bitstream.readBool()
      self.duration_flag = bitstream.readBool()
      bitstream.readBits(5)
      if self.program_splice_flag:
        self.utc_splice_time = bitstream.readBits(32)
      else:
        self.component_count = bitstream.readBits(8)
        self.components = [
          SpliceScheduleEventComponent(bitstream)
          for _ in range(self.component_count)
        ]
      if self.duration_flag:
        self.break_duration = BreakDuration(bitstream)
      self.unique_program_id = bitstream.readBits(16)
      self.avail_num = bitstream.readBits(8)
      self.avails_expected = bitstream.readBits(8)

class SpliceScheduleEventComponent:
  def __init__(self, bitstream):
    self.component_tag = bitstream.readBits(8)
    self.utc_splice_time = bitstream.readBits(32)

class SpliceInsert:
  def __init__(self, bitstream):
    self.splice_event_id = bitstream.readBits(32)
    self.splice_event_cancel_indicator = bitstream.readBool()
    bitstream.readBits(7)
    if not self.splice_event_cancel_indicator:
      self.out_of_network_indicator = bitstream.readBool()
      self.program_splice_flag = bitstream.readBool()
      self.duration_flag = bitstream.readBool()
      self.splice_immediate_flag = bitstream.readBool()
      bitstream.readBits(4)
      if self.program_splice_flag and not self.splice_immediate_flag:
        self.splice_time = SpliceTime(bitstream)
      if not self.program_splice_flag:
        self.component_count = bitstream.readBits(8)
        self.components = [
          SpliceInsertComponent(bitstream, self.splice_immediate_flag)
          for _ in range(self.component_count)
        ]
      if self.duration_flag:
        self.break_duration = BreakDuration(bitstream)
      self.unique_program_id = bitstream.readBits(16)
      self.avail_num = bitstream.readBits(8)
      self.avails_expected = bitstream.readBits(8)

class SpliceInsertComponent:
  def __init__(self, bitstream, splice_immediate_flag):
    self.component_tag = bitstream.readBits(8)
    if not splice_immediate_flag:
      self.splice_time = SpliceTime(bitstream)

class TimeSignal:
  def __init__(self, bitstream):
    self.splice_time = SpliceTime(bitstream)

class BandwidthReservation:
  def __init__(self, bitstream):
    pass

class PrivateCommand:
  def __init__(self, bitstream, length):
    self.identifier = self.readBits(32)
    self.private_byte = bytes([
      bitstream.readBits(8)
      for _ in range(length - 4)
    ])

class BreakDuration:
  def __init__(self, bitstream):
    self.auto_return = bitstream.readBool()
    bitstream.readBits(6)
    self.duration = bitstream.readBits(33)

class SpliceTime:
  def __init__(self, bitstream):
    self.time_specified_flag = bitstream.readBool()
    if self.time_specified_flag:
      bitstream.readBits(6)
      self.pts_time = bitstream.readBits(33)
    else:
      bitstream.readBits(7)

class Descriptor:
  def __init__(self, bitstream):
    self.descriptor_tag = bitstream.readBits(8)
    self.descriptor_length = bitstream.readBits(8)
    self.identifier = bitstream.readBits(32)

class SpliceDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.private_byte = bytes([
      bitstream.readBits(8)
      for _ in range(self.descriptor_length - 4)
    ])

class AvailDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.provider_avail_id = bitstream.readBits(8)

class DTMFDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.preroll = bitstream.readBits(8)
    self.dtmf_count = bitstream.readBits(3)
    bitstream.readBits(5)
    self.DTMF_char = "".join([
      chr(bitstream.readBits(8))
      for _ in range(self.dtmf_count)
    ])

class SegmentationDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.segmentation_event_id = bitstream.readBits(32)
    self.segmentation_event_cancel_indicator = bitstream.readBool()
    bitstream.readBits(7)
    if not self.segmentation_event_cancel_indicator:
      self.program_segmentation_flag = bitstream.readBool()
      self.segmentation_duration_flag = bitstream.readBool()
      self.delivery_not_restricted_flag = bitstream.readBool()
      if not self.delivery_not_restricted_flag:
        self.web_delivery_allowed_flag = bitstream.readBool()
        self.no_regional_blackout_flag = bitstream.readBool()
        self.archive_allowed_flag = bitstream.readBool()
        self.device_restrictions = bitstream.readBits(2)
      else:
        bitstream.readBits(5)
      if not self.program_segmentation_flag:
        self.component_count = bitstream.readBits(8)
        self.components = [
          SegmentationDescriptorComponent(bitstream)
          for _ in range(self.component_count)
        ]
      if self.segmentation_duration_flag:
        self.segmentation_duration = bitstream.readBits(40)
      self.segmentation_upid_type = bitstream.readBits(8)
      self.segmentation_upid_length = bitstream.readBits(8)
      self.segmentation_upid = bitstream.readBits(self.segmentation_upid_length * 8).to_bytes(8, 'big')
      bitstream.readBits(self.segmentation_upid_length * 8)
      self.segmentation_type_id = bitstream.readBits(8)
      self.segment_num = bitstream.readBits(8)
      self.segments_expected = bitstream.readBits(8)
      if self.segmentation_type_id in [0x34, 0x36, 0x38, 0x3A]:
        self.sub_segment_num = bitstream.readBits(8)
        self.sub_segments_expected = bitstream.readBits(8)

class SegmentationDescriptorComponent:
  def __init__(self, bitstream):
    self.component_tag = bitstream.readBits(8)
    bitstream.readBits(7)
    self.pts_offset = bitstream.readBits(33)

class SegmentationUpid:
  def __init__(self, bitstream):
    pass

class TimeDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.TAI_seconds = bitstream.readBits(48)
    self.TAI_ns = bitstream.readBits(32)
    self.UTC_offset = bitstream.readBits(16)

class AudioDescriptor(Descriptor):
  def __init__(self, bitstream):
    super().__init__(bitstream)
    self.audio_count = bitstream.readBits(4)
    bitstream.readBits(4)
    self.components = [
      AudioDescriptorComponent(bitstream)
      for _ in range(self.audio_count)
    ]

class AudioDescriptorComponent:
  def __init__(self, bitstream):
    self.component_tag = bitstream.readBits(8)
    self.ISO_code = bitstream.readBits(24)
    self.Bit_Stream_Mode = bitstream.readBits(3)
    self.Num_Channels = bitstream.readBits(4)
    self.Full_Srvc_Audio = bitstream.readBool()
