from peer_config import PIECE_SIZE
import struct


class PeerMessage:
    """
    Messages between peers.
    BitTorrent uses Big-Endian (Network Byte Order) for all messages, this is
    declared as the first character being '>' in all pack / unpack calls to the
    Python's `struct` module.
    """
    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9
    Handshake = None  # Handshake is not really part of the messages
    KeepAlive = None  # Keep-alive has no ID according to spec

    def encode(self) -> bytes:
        pass

    @classmethod
    def decode(cls, data: bytes):
        pass

class Handshake(PeerMessage):
    """
    Message format:
        <pstrlen><pstr><reserved><info_hash><peer_id>
        pstrlen = 19
        pstr = "BitTorrent protocol".
    The messages is: 49 + len(pstr) = 68 bytes long.
    """
    length = 49 + 19

    def __init__(self, info_hash: bytes):
        """
        Construct the handshake message
        :param info_hash: The SHA1 hash for the info dict
        :param peer_id: The unique peer id
        """
        if isinstance(info_hash, str):
            info_hash = info_hash.encode('utf-8')
        self.info_hash: bytes = info_hash

    def encode(self) -> bytes:
        """
        Encodes this object instance to the raw bytes representing the entire message (ready to be transmitted).
        """
        return struct.pack(
            '>B19s8s20s20s',
            19,  # Single byte (B)
            b'BitTorrent protocol',  # String 19s
            b"\x00" * 8,  # Reserved 8x (pad byte, no value)
            self.info_hash,  # String 20s
            b"\x00" * 20)  # String 20s

    @classmethod
    def decode(cls, data: bytes):
        """
        Decodes the given BitTorrent message into a handshake message, if not a valid message, return None.
        """
        if len(data) < (49 + 19):
            raise ValueError("Invalid Handshake message length")
        parts = struct.unpack('>B19s8s20s20s', data)
        return cls(info_hash=parts[3])

    @classmethod
    def is_valid(cls, data: bytes):
        if len(data) != 68:
            return False
        if data[:1] != struct.pack("!B", 19) or data[1:20] != b'BitTorrent protocol':
            return False
        return True


class Request(PeerMessage):
    """
    The message used to request a block of a piece (i.e. a partial piece).
    The request size for each block is 256KB
    Message format:
        <len=0013><id=6><index><begin><length>
    """

    def __init__(self, index: int, begin: int, length: int = PIECE_SIZE):
        """
        :param index: The zero based piece index
        :param begin: The zero based offset within a piece
        :param length: The requested length of data (default 256kB)
        """
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return struct.pack('>IbIII',
                           13,
                           PeerMessage.Request,
                           self.index,
                           self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes):
        # Tuple with (message length, id, index, begin, length)
        parts = struct.unpack('>IbIII', data)
        return cls(parts[2], parts[3], parts[4])


class Piece(PeerMessage):
    """
    Message format:
        <length prefix><message ID><index><begin><block>
    """
    length = 9 #The Piece message length without the block data

    def __init__(self, index: int, begin: int, block: bytes):
        """
        :param index: The zero based piece index
        :param begin: The zero based offset within a piece
        :param block: The block data
        """
        self.index = index
        self.begin = begin
        self.block = block

    def encode(self):
        message_length = Piece.length + len(self.block)
        return struct.pack('>IbII' + str(len(self.block)) + 's',
                           message_length,
                           PeerMessage.Piece,
                           self.index,
                           self.begin,
                           self.block)

    @classmethod
    def decode(cls, data: bytes):
        length = struct.unpack('>I', data[:4])[0]
        parts = struct.unpack('>IbII' + str(length - Piece.length) + 's',
                              data[:length + 4])
        return cls(parts[2], parts[3], parts[4])

