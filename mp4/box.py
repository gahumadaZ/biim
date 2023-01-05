
composition_matrix = bytes([
  0x00, 0x01, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x00, 0x01, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00,
  0x40, 0x00, 0x00, 0x00,
])

def box(fourcc, data = b''):
  total = sum(map(len, data)) if type(data) is list else len(data)
  return (8 + total).to_bytes(4, byteorder='big') + fourcc.encode('ascii') + (b''.join(data) if type(data) is list else data)

def fullbox(fourcc, version, flags, data = b''):
  return box(fourcc, [version.to_bytes(1, byteorder='big'), flags.to_bytes(3, byteorder='big'), (b''.join(data) if type(data) is list else data)])

def ftyp():
  return box('ftyp', [
    'isom'.encode('ascii'), # major_brand: isom
    (1).to_bytes(4, byteorder='big'), # minor_version: 0x01
    'isom'.encode('ascii'),
    'avc1'.encode('ascii')
  ])

def moov(mvhd, mvex, trak):
  return box('moov', [
    mvhd,
    mvex,
    b''.join(trak) if type(trak) is list else trak
  ])

def mvhd(timescale):
  return fullbox('mvhd', 0, 0, [
    (0).to_bytes(4, byteorder='big'), # creation_time
    (0).to_bytes(4, byteorder='big'), # modification_time
    timescale.to_bytes(4, byteorder='big'), # timescale
    (0).to_bytes(4, byteorder='big'), # duration
    b'\x00\x01\x00\x00', # Preferred rate: 1.0
    b'\x01\x00\x00\x00', # PreferredVolume(1.0, 2bytes) + reserved(2bytes)
    (0).to_bytes(4 * 2, byteorder='big'), # reserved: 4 + 4 bytes
    composition_matrix, # composition_matrix
    (0).to_bytes(4 * 6, byteorder='big'), # reserved: 6 * 4 bytes
    b'\xFF\xFF\xFF\xFF' # next_track_ID
  ])

def trak(tkhd, mdia):
  return box('trak', tkhd + mdia)

def tkhd(trackId, width, height):
  return fullbox('tkhd', 0, 0, [
    (0).to_bytes(4, byteorder='big'), # creation_time
    (0).to_bytes(4, byteorder='big'), # modification_time
    trackId.to_bytes(4, byteorder='big'), # trackId
    (0).to_bytes(4, byteorder='big'), # reserved: 4 byte
    (0).to_bytes(4, byteorder='big'), # duration
    (0).to_bytes(4 * 2, byteorder='big'), # reserved: 4 + 4 bytes
    (0).to_bytes(4 * 2, byteorder='big'), # layer(2bytes) + alternate_group(2bytes), volume(2bytes) + reserved(2bytes)
    composition_matrix, # composition_matrix
    (width).to_bytes(2, byteorder='big') + b'\x00\x00', # width
    (height).to_bytes(2, byteorder='big') + b'\x00\x00', # height
  ])

def mdia(mdhd, hdlr, minf):
  return box('mdia', [mdhd, hdlr, minf])

def mdhd(timescale):
  return fullbox('mdhd', 0, 0, [
    (0).to_bytes(4, byteorder='big'), # creation_time
    (0).to_bytes(4, byteorder='big'), # modification_time
    timescale.to_bytes(4, byteorder='big'), # timescale
    (0).to_bytes(4, byteorder='big'), # duration
    b'\x55\xC4' + (0).to_bytes(2, byteorder='big'), # language: und (undetermined), pre_defined = 0
  ])

def hdlr(handler_type, handler_name):
  return fullbox('hdlr', 0, 0, [
    (0).to_bytes(4, byteorder='big'), # pre_defined
    handler_type.encode('ascii'), # handler_type
    (3 * 4).to_bytes(3 * 4, byteorder='big'), # reserved: 3 * 4 bytes
    handler_name.encode('ascii') + b'\x00'  # handler_name
  ])

def minf(xmhd, dinf, stbl):
  return box('minf', [
    xmhd or nmhd(),
    dinf,
    stbl
  ])

def nmhd():
  return fullbox('nmhd', 0, 0)

def vmhd():
  return fullbox('vmhd', 0, 1, [
    (0).to_bytes(2, byteorder='big'), # graphicsmode: 2 bytes
    (0).to_bytes(6, byteorder='big'), # opcolor: 3 * 2 bytes
  ])

def smhd():
  return fullbox('smhd', 0, 1, [
    (0).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # balance(2) + reserved(2)
  ])

def dinf():
  return box('dinf',
    fullbox('dref', 0, 0, [(1).to_bytes(4, byteorder='big'), fullbox('url ', 0, 1)])
  )

def stbl(stsd):
  return box('stbl', [
    stsd,
    fullbox('stts', 0, 0, (0).to_bytes(4, byteorder='big')),
    fullbox('stsc', 0, 0, (0).to_bytes(4, byteorder='big')),
    fullbox('stsz', 0, 0, (0).to_bytes(8, byteorder='big')),
    fullbox('stco', 0, 0, (0).to_bytes(4, byteorder='big')),
  ])

def stsd(codec):
  return fullbox('stsd', 0, 1, [
    (1).to_bytes(4, byteorder='big'),
    codec
  ])

def mp4a(config, channelCount, sampleRate):
  return box('mp4a', [
    (0).to_bytes(4, byteorder='big'), # reserved(4)
    (0).to_bytes(2, byteorder='big'), (1).to_bytes(2, byteorder='big'), # reserved(2) + data_reference_index(2)
    (0).to_bytes(4 * 2, byteorder='big'), # reserved(8)
    (channelCount).to_bytes(2, byteorder='big'), (0x10).to_bytes(2, byteorder='big'), # channelCount(2) + sampleSize(2)
    (0).to_bytes(4, byteorder='big'), # reserved(4)
    (sampleRate).to_bytes(2, byteorder='big'), (0x00).to_bytes(2, byteorder='big'), # sampleRate(2) +  sampleSize(2)
    esds(config, bytes([ 0x06, 0x01, 0x02 ])), # with GASpecificConfig
  ])

def esds(config, descriptor = b''):
  return fullbox('esds', 0, 0, [
    (0x03).to_bytes(1, byteorder='big'), # descriptor_type
    (0x17 + len(config)).to_bytes(1, byteorder='big'), # length
    (0x01).to_bytes(2, byteorder='big'), # es_id
    (0).to_bytes(1, byteorder='big'), # stream_priority
    (0x04).to_bytes(1, byteorder='big'), # descriptor_type
    (0x0F + len(config)).to_bytes(1, byteorder='big'), # length
    (0x40).to_bytes(1, byteorder='big'), # codec: mpeg4_audio
    (0x15).to_bytes(1, byteorder='big'), # stream_type: Audio
    (0).to_bytes(3, byteorder='big'), #  buffer_size
    (0).to_bytes(4, byteorder='big'), # maxBitrate
    (0).to_bytes(4, byteorder='big'), # avgBitrate
    (0x05).to_bytes(1, byteorder='big'), # descriptor_type
    (len(config)).to_bytes(1, byteorder='big'), #  length
    config,
    descriptor,
  ])

def avc1(config, width, height):
  return box('avc1', [
    (0).to_bytes(4, byteorder='big'), # rereserved(4)
    (0).to_bytes(2, byteorder='big'), (1).to_bytes(2, byteorder='big'), # reserved(2) + data_reference_index(2)
    (0).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # pre_defined(2) + reserved(2)
    (0).to_bytes(3 * 4, byteorder='big'), # pre_defined: 3 * 4 bytes
    (width).to_bytes(2, byteorder='big'), (height).to_bytes(2, byteorder='big'), # width 2bytes, height: 2 bytes
    (0x48).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # horizresolution: 4 bytes divide 2bytes
    (0x48).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # vertresolution: 4 bytes divide 2bytes
    (0).to_bytes(4, byteorder='big'), # rereserved(4)
    (1).to_bytes(2, byteorder='big'), # frame_count
    (0).to_bytes(32, byteorder='big'), # compressorname (strlen, 1byte, total 32bytes)
    (0x18).to_bytes(2, byteorder='big'), b'\xFF\xFF', # depth, pre_defined = -1
    box('avcC', config)
  ])

def hvc1(config, width, height):
  return box('hvc1', [
    (0).to_bytes(4, byteorder='big'), # rereserved(4)
    (0).to_bytes(2, byteorder='big'), (1).to_bytes(2, byteorder='big'), # reserved(2) + data_reference_index(2)
    (0).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # pre_defined(2) + reserved(2)
    (0).to_bytes(3 * 4, byteorder='big'), # pre_defined: 3 * 4 bytes
    (width).to_bytes(2, byteorder='big'), (height).to_bytes(2, byteorder='big'), # width 2bytes, height: 2 bytes
    (0x48).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # horizresolution: 4 bytes divide 2bytes
    (0x48).to_bytes(2, byteorder='big'), (0).to_bytes(2, byteorder='big'), # vertresolution: 4 bytes divide 2bytes
    (0).to_bytes(4, byteorder='big'), # rereserved(4)
    (1).to_bytes(2, byteorder='big'), # frame_count
    (0).to_bytes(32, byteorder='big'), # compressorname (strlen, 1byte, total 32bytes)
    (0x18).to_bytes(2, byteorder='big'), b'\xFF\xFF', # depth, pre_defined = -1
    box('hvcC', config)
  ])

def wvtt():
  return box('wvtt', [
    (0).to_bytes(6, byteorder='big') + # ???
    (1).to_bytes(2, byteorder='big') + # dataReferenceIndex
    vttC()
  ])

def vttC():
  return box('vttC', 'WEBVTT\n'.encode('ascii'))

def mvex(trex):
  return box('mvex', b''.join(trex) if type(trex) is list else trex)

def trex(trackId):
  return fullbox('trex', 0, 0, [
    trackId.to_bytes(4, byteorder='big'), # trackId
    (1).to_bytes(4, byteorder='big'), # default_sample_description_index
    (0).to_bytes(4, byteorder='big'), # default_sample_duration
    (0).to_bytes(4, byteorder='big'), # default_sample_size
    b'\x00\x01\x00\x01' # default_sample_flags
  ])

def moof(sequence_number, fragments):
  moofSize = len(
    box('moof', [
      mfhd(sequence_number),
      b''.join([traf(trackId, duration, baseMediaDecodeTime, offset, samples) for trackId, duration, baseMediaDecodeTime, offset, samples in fragments])
    ])
  )
  return box('moof', [
    mfhd(sequence_number),
    b''.join([traf(trackId, duration, baseMediaDecodeTime, moofSize + 8 + offset, samples) for trackId, duration, baseMediaDecodeTime, offset, samples in fragments])
  ])

def mfhd(sequence_number): # 20 bytes
  return fullbox('mfhd', 0, 0, [
    (0).to_bytes(4, byteorder='big'),
    (sequence_number).to_bytes(4, byteorder='big')
  ])

def traf(trackId, duration, baseMediaDecodeTime, offset, samples):
  return box('traf', [
    tfhd(trackId, duration),
    tfdt(baseMediaDecodeTime),
    trun(offset, samples),
  ])

def tfhd(trackId, duraiton):
  return fullbox('tfhd', 0, 8, [
    (trackId).to_bytes(4, byteorder='big'),
    (duraiton).to_bytes(4, byteorder='big')
  ])

def tfdt(baseMediaDecodeTime):
  return fullbox('tfdt', 1, 0, baseMediaDecodeTime.to_bytes(8, byteorder='big'))

def trun(offset, samples):
  return fullbox('trun', 0, 0x000F01, [
    (len(samples)).to_bytes(4, byteorder='big'),
    (offset).to_bytes(4, byteorder='big'),
    b''.join([
      b''.join([
          (duration).to_bytes(4, byteorder='big'),
          (size).to_bytes(4, byteorder='big'),
          (2 if isKeyframe else 1).to_bytes(1, byteorder='big'),
          (((1 if isKeyframe else 0) << 6) | ((0 if isKeyframe else 1) << 0)).to_bytes(1, byteorder='big'),
          (0).to_bytes(2, byteorder='big'),
          (compositionTimeOffset).to_bytes(4, byteorder='big'),
      ]) for size, duration, isKeyframe, compositionTimeOffset in samples
    ])
  ])

def mdat(data):
  return box('mdat', data)

def emsg(timescale, presentationTime, duration, schemeIdUri, content):
  return fullbox('emsg', 1, 0, [
    (timescale).to_bytes(4, byteorder='big'),
    (presentationTime).to_bytes(8, byteorder='big'),
    (duration if duration is not None else 0xFFFFFFFF).to_bytes(4, byteorder='big'),
    (0).to_bytes(4, byteorder='big'), # id
    (schemeIdUri).encode('ascii') + b'\x00',
    b'\x00', # value
    content
  ])