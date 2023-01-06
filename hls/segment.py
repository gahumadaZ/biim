#!/usr/bin/env python3

import math
import asyncio
from datetime import datetime, timedelta

from mpeg2ts import ts

class PartialSegment:
  def __init__(self, beginPTS, isIFrame = False):
    self.beginPTS = beginPTS
    self.endPTS = None
    self.hasIFrame = isIFrame
    self.buffer = bytearray()
    self.futures = []
    self.m3u8s = []

  def push(self, packet):
    self.buffer += packet

  def future(self):
    f = asyncio.Future()
    if (self.isCompleted()):
      f.set_result(bytes(self.buffer))
    else:
      self.futures.append(f)
    return f

  def m3u8(self):
    f = asyncio.Future()
    if not self.isCompleted():
      self.m3u8s.append(f)
    return f

  def complete(self, endPTS):
    self.endPTS = endPTS
    for f in self.futures:
      if not f.done(): f.set_result(bytes(self.buffer))

  def isCompleted(self):
    return self.endPTS is not None

  def extinf(self):
    if not self.endPTS:
      return None
    else:
      return timedelta(seconds = (((self.endPTS - self.beginPTS + ts.PCR_CYCLE) % ts.PCR_CYCLE) / ts.HZ))

  def estimate(self, endPTS):
    return timedelta(seconds = (((endPTS - self.beginPTS + ts.PCR_CYCLE) % ts.PCR_CYCLE) / ts.HZ))

class Segment(PartialSegment):
  def __init__(self, beginPTS, isIFrame = False):
    super().__init__(beginPTS, isIFrame = False)
    self.partials = [PartialSegment(beginPTS, isIFrame)]
    self.program_date_time = datetime.now()

  def __iter__(self):
    return iter(self.partials)

  def __len__(self):
    return len(self.parital)

  def push(self, packet):
    super().push(packet)
    if not self.partials: return
    self.partials[-1].push(packet)

  def completePartial(self, endPTS):
    if not self.partials: return
    self.partials[-1].complete(endPTS)

  def newPartial(self, beginPTS, isIFrame = False):
    self.partials.append(PartialSegment(beginPTS, isIFrame))

  def complete(self, endPTS):
    super().complete(endPTS)
    self.completePartial(endPTS)

