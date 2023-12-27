import asyncio
import base64
import ssl
import logging
import contextlib
from typing import Callable, Tuple
import util.util as util
from ssh.version import parse_version 
from http3.http3_client import *
from ssh.resources_manager import *

log = logging.getLogger(__name__)

class ConversationID:
    def __init__(self, value: bytes):
        self.value = value # 32 bytes
        assert len(value) <= 32

    def __str__(self):
        return base64.b64encode(self.value).decode('utf-8')

from ssh.channel import *
import secrets

def random_bytes(length: int) -> bytes:
    return secrets.token_bytes(length)


def generate_conversation_id(tls_connection_state: ssl.SSLObject) -> Tuple[bytes, Exception]:
    return random_bytes(32), None
    # try: # TODO
    #     if not tls_connection_state:
    #         return b'', Exception("TLS connection state is None")
    #     key_material = tls_connection_state.export_keying_material("EXPORTER-SSH3", 32)
    #     if len(key_material) != 32:
    #         raise ValueError(f"TLS returned a tls-exporter with the wrong length ({len(key_material)} instead of 32)")
    #     return key_material, None
    # except Exception as e:
    #     return b'', e
    
class Conversation:
    def __init__(self, control_stream, max_packet_size, default_datagrams_queue_size, stream_creator, message_sender, channels_manager, conversation_id):
        self.control_stream = control_stream
        self.max_packet_size = max_packet_size
        self.default_datagrams_queue_size = default_datagrams_queue_size
        self.stream_creator = stream_creator
        self.message_sender = message_sender
        self.channels_manager = channels_manager
        self.context = None  # Will be set using context manager
        self.cancel_context = None  # Will be set using context manager
        self.conversation_id = conversation_id
        self.channels_accept_queue = None  # Set to an appropriate queue type

    def __init__(self, max_packet_size, default_datagrams_queue_size, tls: ssl.SSLContext):
        self.conv_id, err = generate_conversation_id(tls)
        if err:
            log.error(f"could not generate conversation ID: {err}")
            raise err

        self.control_stream = None
        self.channels_accept_queue = util.AcceptQueue()  # Assuming a suitable implementation
        self.stream_creator = None
        self.max_packet_size = max_packet_size
        self.default_datagrams_queue_size = default_datagrams_queue_size
        self.channels_manager = ChannelsManager()  # Assuming a suitable implementation
        self.conversation_id = self.conv_id
        
    async def establish_client_conversation(self, request, round_tripper: HttpClient):
        # Stream hijacker
        def stream_hijacker(frame_type, stream_id, data, end_stream):
            # Your stream hijacking logic
            """
            Process data received on a hijacked stream.
            
            :param frame_type: The type of frame received (inferred from the data)
            :param stream_id: The ID of the stream
            :param data: The data received on the stream
            :param end_stream: Flag indicating if the stream has ended
            """
            if frame_type != SSH_FRAME_TYPE:
                # If the frame type is not what we're interested in, ignore it
                return False, None

            try:
                # Parse the header from the data
                control_stream_id, channel_type, max_packet_size = parse_header(stream_id, data)
                
                 # Create a new channel
                channel_info = ChannelInfo(
                    conversation_id=self.conversation_id,
                    conversation_stream_id=control_stream_id,
                    channel_id=stream_id,
                    channel_type=channel_type,
                    max_packet_size=max_packet_size
                )

                new_channel = Channel(
                    channel_info.conversation_stream_id,
                    channel_info.conversation_id,
                    channel_info.channel_id,
                    channel_info.channel_type,
                    channel_info.max_packet_size,
                    stream_reader=None,  # Replace with the actual stream reader
                    stream_writer=None,  # Replace with the actual stream writer
                    channels_manager=self.channels_manager,
                    default_datagrams_queue_size=self.default_datagrams_queue_size
                )
                # Set the datagram sender and add the new channel to the queue
                new_channel.set_datagram_sender(self.get_datagram_sender_for_channel(new_channel.channel_id))
                self.channels_accept_queue.add(new_channel)

                return True, None
            except Exception as e:
                # Log the error and return False with the error
                log.error(f"Error in stream hijacker: {e}")
                return False, e


        # Assigning the hijacker to the round_tripper
        round_tripper._stream_handler = stream_hijacker
        
        log.debug(f"Establishing conversation with server: {request}")

        # Performing the HTTP request
        # response = await request
        response = await round_tripper._request(request)
        log.debug(f"Established conversation with server: {response}")
        server_version = response.headers.get("server")
        log.debug(f"Established conversation with server: {server_version}")
        major, minor, patch = parse_version(server_version)

        if response.status_code == 200:
            self.control_stream = response.http_stream
            self.stream_creator = response.stream_creator
            self.message_sender = response.http_connection._quic
            await self.handle_datagrams(round_tripper)
            return None
        elif response.status_code == 401:
            raise Exception("Authentication failed")
        else:
            raise Exception(f"Returned non-200 and non-401 status code: {response.status_code}")

    async def handle_datagrams(self, connection):
        while True:
            try:
                datagram = await connection.datagram_received()
                # Process datagram
                # ...
            except asyncio.CancelledError:
                break
            
async def new_client_conversation(max_packet_size, queue_size, tls_state):
    # Additional logic for creating a new client conversation
    return Conversation(max_packet_size, queue_size, tls_state)

