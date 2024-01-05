from typing import BinaryIO, Callable, Deque, Dict, List, Optional, Union, cast


import aioquic
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, ErrorCode, H3Connection
from aioquic.h3.events import (
    DataReceived,
    H3Event,
    HeadersReceived,
    PushPromiseReceived,
)

from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import DatagramFrameReceived, QuicEvent, StreamDataReceived
from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import CipherSuite, SessionTicket

class QuicClient(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.pushes: Dict[int, Deque[H3Event]] = {}
        self._request_events: Dict[int, Deque[H3Event]] = {}
        self._request_waiter: Dict[int, asyncio.Future[Deque[H3Event]]] = {}
        self._http = H3Connection(self._quic)

    def http_event_received(self, event: H3Event) -> None:
        if isinstance(event, (HeadersReceived, DataReceived)):
            print(f"http_event_received -> event -> {event}")
            stream_id = event.stream_id
            if stream_id in self._request_events:
                # http
                self._request_events[event.stream_id].append(event)
                if event.stream_ended:
                    request_waiter = self._request_waiter.pop(stream_id)
                    request_waiter.set_result(self._request_events.pop(stream_id))

            elif event.push_id in self.pushes:
                # push
                self.pushes[event.push_id].append(event)
        elif isinstance(event, PushPromiseReceived):
            self.pushes[event.push_id] = deque()
            self.pushes[event.push_id].append(event)

    def quic_event_received(self, event: QuicEvent) -> None:
        #  pass event to the HTTP layer
       
        if self._http is not None:
            if isinstance(event, StreamDataReceived):
                print(f"handle_event({event.stream_id}) res -> {self._http.handle_event(event)}")
                stream = self._http._get_or_create_stream(event.stream_id)
                http_event = DataReceived(
                    data=event.data,
                    push_id=stream.push_id,
                    stream_id=stream.stream_id,
                    stream_ended=True,
                )
                self.http_event_received(http_event)
            for http_event in self._http.handle_event(event):
                print(f"quic_event_received -> {http_event}")
                self.http_event_received(http_event)

    def send_data(self, data) -> None:
        stream_id = self._quic.get_next_available_stream_id()
        print(f"stream_id -> {stream_id}")
        self._http._quic.send_stream_data(
            stream_id, data, end_stream=True
        )
        # waiter = self._loop.create_future()
        # self._request_events[stream_id] = deque()
        # self._request_waiter[stream_id] = waiter
        self.transmit()

        # return await asyncio.shield(waiter)

    async def _request(self) -> Deque[H3Event]:
        stream_id = self._quic.get_next_available_stream_id()
        print(f"stream_id -> {stream_id}")
        path = b"GET /Cargo.toml\r\n"
        self._http._quic.send_stream_data(
            stream_id, path, end_stream=True
        )
        waiter = self._loop.create_future()
        self._request_events[stream_id] = deque()
        self._request_waiter[stream_id] = waiter
        self.transmit()

        return await asyncio.shield(waiter)
