#!/usr/bin/env python3

import asyncio
from aiohttp import web

import argparse
import sys
import os

from collections import deque

from pathlib import Path
from datetime import datetime, timedelta, timezone
import textwrap

from mpeg2ts import ts
from mpeg2ts.packetize import packetize_section, packetize_pes
from mpeg2ts.section import Section
from mpeg2ts.pat import PATSection
from mpeg2ts.pmt import PMTSection
from mpeg2ts.pes import PES
from mpeg2ts.h265 import H265PES
from mpeg2ts.parser import SectionParser, PESParser

from hls.m3u8 import M3U8

from mp4.box import ftyp, moov, mvhd, mvex, trex, moof, mdat, emsg
from mp4.hevc import hevcTrack
from mp4.mp4a import mp4aTrack

SAMPLING_FREQUENCY = {
  0x00: 96000,
  0x01: 88200,
  0x02: 64000,
  0x03: 48000,
  0x04: 44100,
  0x05: 32000,
  0x06: 24000,
  0x07: 22050,
  0x08: 16000,
  0x09: 12000,
  0x0a: 11025,
  0x0b: 8000,
  0x0c: 7350,
}

async def main():
  loop = asyncio.get_running_loop()
  parser = argparse.ArgumentParser(description=('biim: LL-HLS origin'))

  parser.add_argument('-i', '--input', type=argparse.FileType('rb'), nargs='?', default=sys.stdin.buffer)
  parser.add_argument('-s', '--SID', type=int, nargs='?')
  parser.add_argument('-l', '--list_size', type=int, nargs='?')
  parser.add_argument('-t', '--target_duration', type=int, nargs='?', default=1)
  parser.add_argument('-p', '--part_duration', type=float, nargs='?', default=0.1)
  parser.add_argument('--port', type=int, nargs='?', default=8080)

  args = parser.parse_args()

  video_m3u8 = M3U8(args.target_duration, args.part_duration, args.list_size, True, 'v_')
  p_audio_m3u8 = M3U8(args.target_duration, args.part_duration, args.list_size, True, 'p_a_')
  s_audio_m3u8 = M3U8(args.target_duration, args.part_duration, args.list_size, True, 's_a_')
  video_init, p_audio_init, s_audio_init = asyncio.Future(), asyncio.Future(), asyncio.Future()
  availabilityStartTime = datetime.now(timezone.utc)

  async def master(request):
    text = ''
    text += f'#EXTM3U\n'
    text += f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="Audio",LANGUAGE="jp",NAME="主音声",AUTOSELECT=YES,DEFAULT=YES,URI="p_a_playlist.m3u8"\n'
    text += f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="Audio",LANGUAGE="jp",NAME="副音声",AUTOSELECT=NO,URI="s_a_playlist.m3u8"\n'
    text += f'#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="Audio"\n'
    text += f'v_playlist.m3u8\n'
    return web.Response(headers={'Access-Control-Allow-Origin': '*'}, text=text, content_type="application/x-mpegURL")

  async def mpd(request):
    text = textwrap.dedent(f"""
      <?xml version="1.0" encoding="utf-8"?>
      <MPD xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns="urn:mpeg:dash:schema:mpd:2011"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        xsi:schemaLocation="urn:mpeg:DASH:schema:MPD:2011 http://standards.iso.org/ittf/PubliclyAvailableStandards/MPEG-DASH_schema_files/DASH-MPD.xsd"
        profiles="urn:mpeg:dash:profile:isoff-live:2011"
        type="dynamic"
        minimumUpdatePeriod="PT500S"
        availabilityStartTime="{(availabilityStartTime).isoformat()}"
        publishTime="{datetime.now(timezone.utc).isoformat()}"
        timeShiftBufferDepth="PT1M0.0S"
        maxSegmentDuration="PT0.5S"
        minBufferTime="PT0.0S">
        <ProgramInformation>
        </ProgramInformation>
        <ServiceDescription id="0">
        </ServiceDescription>
        <Period id="0" start="PT0.0S">
          <AdaptationSet id="0" contentType="video" startWithSAP="1" segmentAlignment="true" bitstreamSwitching="true" frameRate="30/1" maxWidth="700" maxHeight="60" par="35:3">
            <Representation id="0" mimeType="video/mp4" codecs="hvc1" bandwidth="328974" width="700" height="60" sar="1:1">
              <SegmentTemplate timescale="90000" duration="45000" availabilityTimeOffset="0.000" initialization="v_init" media="v_segment?msn=$Number%d$" startNumber="0">
              </SegmentTemplate>
            </Representation>
          </AdaptationSet>
          <AdaptationSet id="1" contentType="audio" startWithSAP="1" segmentAlignment="true" bitstreamSwitching="true">
            <Representation id="1" mimeType="audio/mp4" codecs="mp4a.40.2" bandwidth="128000" audioSamplingRate="44100">
              <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2" />
              <SegmentTemplate timescale="90000" duration="45000" availabilityTimeOffset="0.000" initialization="p_a_init" media="p_a_segment?msn=$Number%d$" startNumber="0">
              </SegmentTemplate>
            </Representation>
          </AdaptationSet>
        </Period>
        <UTCTiming schemeIdUri="urn:mpeg:dash:utc:http-xsdate:2014" value="https://time.akamai.com/?iso"/>
      </MPD>
    """).lstrip()
    return web.Response(headers={'Access-Control-Allow-Origin': '*'}, text=text, content_type="application/x-mpegURL")


  def generate_handler(m3u8, init, prefix):
    async def playlist(request):
      nonlocal m3u8
      msn = request.query['_HLS_msn'] if '_HLS_msn' in request.query else None
      part = request.query['_HLS_part'] if '_HLS_part' in request.query else None

      if msn is None and part is None:
        return web.Response(headers={'Access-Control-Allow-Origin': '*'}, text=m3u8.manifest(), content_type="application/x-mpegURL")
      else:
        msn = int(msn)
        if part is None: part = 0
        part = int(part)
        future = m3u8.future(msn, part)
        if future is None:
          return web.Response(headers={'Access-Control-Allow-Origin': '*'}, status=400, content_type="application/x-mpegURL")

        result = await future
        return web.Response(headers={'Access-Control-Allow-Origin': '*'}, text=result, content_type="application/x-mpegURL")
    async def segment(request):
      nonlocal m3u8
      msn = request.query['msn'] if 'msn' in request.query else None

      if msn is None: msn = 0
      msn = int(msn)
      future = m3u8.segment(msn)
      if future is None:
        return web.Response(headers={'Access-Control-Allow-Origin': '*'}, status=400, content_type="video/mp4")

      body = await future
      return web.Response(headers={'Access-Control-Allow-Origin': '*'}, body=body, content_type="video/mp4")
    async def partial(request):
      nonlocal m3u8
      msn = request.query['msn'] if 'msn' in request.query else None
      part = request.query['part'] if 'part' in request.query else None

      if msn is None: msn = 0
      msn = int(msn)
      if part is None: part = 0
      part = int(part)
      future = m3u8.partial(msn, part)
      if future is None:
        return web.Response(headers={'Access-Control-Allow-Origin': '*'}, status=400, content_type="video/mp4")

      body = await future
      return web.Response(headers={'Access-Control-Allow-Origin': '*'}, body=body, content_type="video/mp4")
    async def initalization(request):
      if init is None:
        return web.Response(headers={'Access-Control-Allow-Origin': '*'}, status=400, content_type="video/mp4")

      body = await asyncio.shield(init)
      return web.Response(headers={'Access-Control-Allow-Origin': '*'}, body=body, content_type="video/mp4")
    return playlist, segment, partial, initalization
  video_playlist, video_segment, video_partial, video_initalization = generate_handler(video_m3u8, video_init, "v_")
  p_audio_playlist, p_audio_segment, p_audio_partial, p_audio_initalization = generate_handler(p_audio_m3u8, p_audio_init, "p_a_")
  s_audio_playlist, s_audio_segment, s_audio_partial, s_audio_initalization = generate_handler(s_audio_m3u8, s_audio_init, "s_a_")

  # setup aiohttp
  app = web.Application()
  app.add_routes([
    web.get('/master.m3u8', master),
    web.get('/master.mpd', mpd),

    web.get('/v_playlist.m3u8', video_playlist),
    web.get('/v_segment', video_segment),
    web.get('/v_part', video_partial),
    web.get('/v_init', video_initalization),

    web.get('/p_a_playlist.m3u8', p_audio_playlist),
    web.get('/p_a_segment', p_audio_segment),
    web.get('/p_a_part', p_audio_partial),
    web.get('/p_a_init', p_audio_initalization),

    web.get('/s_a_playlist.m3u8', s_audio_playlist),
    web.get('/s_a_segment', s_audio_segment),
    web.get('/s_a_part', s_audio_partial),
    web.get('/s_a_init', s_audio_initalization),
  ])
  runner = web.AppRunner(app)
  await runner.setup()
  await loop.create_server(runner.server, '0.0.0.0', args.port)

  # setup reader
  PAT_Parser = SectionParser(PATSection)
  PMT_Parser = SectionParser(PMTSection)
  H265_PES_Parser = PESParser(H265PES)
  ID3_PES_Parser = PESParser(PES)
  AAC_PES_Parsers = dict()

  PMT_PID = None
  PCR_PID = None
  H265_PID = None
  ID3_PID = None

  AAC_PIDS = []
  FST_AAC_PID = None
  SND_AAC_PID = None
  FST_AAC_CONFIG = None
  SND_AAC_CONFIG = None

  H265_DEQUE = deque()
  H265_FRAGMENTS = deque()
  EMSG_FRAGMENTS = deque()
  AAC_FRAGMENTS_LIST = []

  AAC_INITS = [p_audio_init, s_audio_init]
  AAC_M3U8S = [p_audio_m3u8, s_audio_m3u8]

  VPS = None
  SPS = None
  PPS = None

  PARTIAL_BEGIN_TIMESTAMP = None

  reader = asyncio.StreamReader()
  protocol = asyncio.StreamReaderProtocol(reader)
  await loop.connect_read_pipe(lambda: protocol, args.input)

  while True:
    isEOF = False
    while True:
      try:
        sync_byte = await reader.readexactly(1)
        if sync_byte == ts.SYNC_BYTE:
          break
      except asyncio.IncompleteReadError:
        isEOF = True
    if isEOF:
      break

    packet = None
    try:
      packet = ts.SYNC_BYTE + await reader.readexactly(ts.PACKET_SIZE - 1)
    except asyncio.IncompleteReadError:
      break

    if ts.pid(packet) == 0x00:
      PAT_Parser.push(packet)
      for PAT in PAT_Parser:
        if PAT.CRC32() != 0: continue
        LAST_PAT = PAT

        for program_number, program_map_PID in PAT:
          if program_number == 0: continue

          if program_number == args.SID:
            PMT_PID = program_map_PID
          elif not PMT_PID and not args.SID:
            PMT_PID = program_map_PID

    elif ts.pid(packet) == PMT_PID:
      PMT_Parser.push(packet)
      for PMT in PMT_Parser:
        if PMT.CRC32() != 0: continue
        LAST_PMT = PMT

        PCR_PID = PMT.PCR_PID
        for stream_type, elementary_PID in PMT:
          if stream_type == 0x24:
            H265_PID = elementary_PID
          elif stream_type == 0x0F:
            if elementary_PID not in AAC_PIDS and len(AAC_PIDS) < 2:
              AAC_PIDS.append(elementary_PID)
              AAC_PES_Parsers[elementary_PID] = PESParser(PES)
              AAC_FRAGMENTS_LIST.append(deque())
          elif stream_type == 0x15:
            ID3_PID = elementary_PID

    elif ts.pid(packet) == ID3_PID:
      ID3_PES_Parser.push(packet)
      for ID3_PES in ID3_PES_Parser:
        timestamp = ID3_PES.pts()
        ID3 = ID3_PES.PES_packet_data()
        EMSG_FRAGMENTS.append(emsg(ts.HZ, timestamp, None, 'https://aomedia.org/emsg/ID3', ID3))

    elif ts.pid(packet) in AAC_PIDS:
      index = AAC_PIDS.index(ts.pid(packet))
      if ts.pid(packet) not in AAC_PES_Parsers: continue
      AAC_PES_Parser = AAC_PES_Parsers[ts.pid(packet)]

      AAC_PES_Parser.push(packet)
      for AAC_PES in AAC_PES_Parser:
        timestamp = AAC_PES.pts()
        begin, ADTS_AAC = 0, AAC_PES.PES_packet_data()
        while begin < len(ADTS_AAC):
          profile = ((ADTS_AAC[begin + 2] & 0b11000000) >> 6)
          samplingFrequencyIndex = ((ADTS_AAC[begin + 2] & 0b00111100) >> 2)
          channelConfiguration = ((ADTS_AAC[begin + 2] & 0b00000001) << 2) | ((ADTS_AAC[begin + 3] & 0b11000000) >> 6)
          frameLength = ((ADTS_AAC[begin + 3] & 0x03) << 11) | (ADTS_AAC[begin + 4] << 3) | ((ADTS_AAC[begin + 5] & 0xE0) >> 5)

          if not AAC_INITS[index].done():
            AAC_CONFIG = (bytes([
              ((profile + 1) << 3) | ((samplingFrequencyIndex & 0x0E) >> 1),
              ((samplingFrequencyIndex & 0x01) << 7) | (channelConfiguration << 3)
            ]), channelConfiguration, SAMPLING_FREQUENCY[samplingFrequencyIndex])
            AAC_INITS[index].set_result(b''.join([
              ftyp(),
              moov(
                mvhd(ts.HZ),
                mvex([
                  trex(1),
                ]),
                [
                  mp4aTrack(1, ts.HZ, *AAC_CONFIG),
                ]
              )
            ]))

          duration = 1024 * ts.HZ // SAMPLING_FREQUENCY[samplingFrequencyIndex]
          AAC_FRAGMENTS_LIST[index].append(
            b''.join([
              moof(0,
                [
                  (1, duration, timestamp, 0, [(frameLength - 7, duration, False, 0)])
                ]
              ),
              mdat(bytes(ADTS_AAC[begin + 7: begin + frameLength]))
            ])
          )
          timestamp += duration
          begin += frameLength

    elif ts.pid(packet) == H265_PID:
      H265_PES_Parser.push(packet)
      for H265 in H265_PES_Parser:
        hasIDR = False
        timestamp = H265.dts() or H265.pts()
        cts =  H265.pts() - timestamp

        for ebsp in H265:
          nal_unit_type = (ebsp[0] >> 1) & 0x3f

          if nal_unit_type == 0x20: # VPS
            VPS = ebsp
          elif nal_unit_type == 0x21: # SPS
            SPS = ebsp
          elif nal_unit_type == 0x22: # PPS
            PPS = ebsp
          elif nal_unit_type == 0x23: # AUD
            pass
          elif nal_unit_type == 39 or nal_unit_type == 40: # SEI
            pass
          else:
            H265_DEQUE.append((nal_unit_type, ebsp, timestamp, cts))

        while len(H265_DEQUE) > 1:
          (nalu_type, ebsp, curr_pts, cts) = H265_DEQUE.popleft()
          (_, _, next_pts, _) = H265_DEQUE[0]
          isKeyframe = (nalu_type == 19 or nalu_type == 20 or nalu_type == 21)
          hasIDR = hasIDR or isKeyframe
          duration = (next_pts - curr_pts + ts.HZ) % ts.HZ
          H265_FRAGMENTS.append(
            b''.join([
              moof(0,
                [
                  (1, duration, curr_pts, 0, [(4 + len(ebsp), duration, isKeyframe, cts)])
                ]
              ),
              mdat(len(ebsp).to_bytes(4, byteorder='big') + ebsp)
            ])
          )

        if VPS and SPS and PPS and not video_init.done():
          video_init.set_result(b''.join([
            ftyp(),
            moov(
              mvhd(ts.HZ),
              mvex([
                trex(1),
              ]),
              [
                hevcTrack(1, ts.HZ, VPS, SPS, PPS),
              ]
            )
          ]))

        if hasIDR:
          PARTIAL_BEGIN_TIMESTAMP = timestamp
          video_m3u8.completeSegment(PARTIAL_BEGIN_TIMESTAMP)
          p_audio_m3u8.completeSegment(PARTIAL_BEGIN_TIMESTAMP)
          s_audio_m3u8.completeSegment(PARTIAL_BEGIN_TIMESTAMP)
          video_m3u8.newSegment(PARTIAL_BEGIN_TIMESTAMP, True)
          p_audio_m3u8.newSegment(PARTIAL_BEGIN_TIMESTAMP, True)
          s_audio_m3u8.newSegment(PARTIAL_BEGIN_TIMESTAMP, True)
        elif PARTIAL_BEGIN_TIMESTAMP is not None:
          PART_DIFF = (timestamp - PARTIAL_BEGIN_TIMESTAMP + ts.PCR_CYCLE) % ts.PCR_CYCLE
          if args.part_duration * ts.HZ < PART_DIFF:
            PARTIAL_BEGIN_TIMESTAMP = timestamp
            video_m3u8.completePartial(PARTIAL_BEGIN_TIMESTAMP)
            p_audio_m3u8.completePartial(PARTIAL_BEGIN_TIMESTAMP)
            s_audio_m3u8.completePartial(PARTIAL_BEGIN_TIMESTAMP)
            video_m3u8.newPartial(PARTIAL_BEGIN_TIMESTAMP)
            p_audio_m3u8.newPartial(PARTIAL_BEGIN_TIMESTAMP)
            s_audio_m3u8.newPartial(PARTIAL_BEGIN_TIMESTAMP)

        while (EMSG_FRAGMENTS): video_m3u8.push(EMSG_FRAGMENTS.popleft())
        while (H265_FRAGMENTS): video_m3u8.push(H265_FRAGMENTS.popleft())
        for index, AAC_FRAGMENTS in enumerate(AAC_FRAGMENTS_LIST):
          while AAC_FRAGMENTS: AAC_M3U8S[index].push(AAC_FRAGMENTS.popleft())
    else:
      pass

if __name__ == '__main__':
  asyncio.run(main())
