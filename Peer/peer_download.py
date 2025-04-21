import hashlib
import os
from enum import Enum
from typing import Optional, List, Dict
import aiofiles

from peer_config import LOG_DIR, DOWNLOAD_DIR, get_unique_filename, logger
from peer_torrent import TorrentFile
from peer_message import *

class PieceStatus(Enum):
    MISSING = 0
    PENDING = 1
    COMPLETED = 2

class PieceManage:
    def __init__(self, torrent: TorrentFile, output_dir: str):
        self.torrent: TorrentFile = torrent
        self.completed: bool = False
        self.pieces_status: List[PieceStatus] = [PieceStatus.MISSING] * self.torrent.number_of_pieces
        self.haveMultiFile: bool = torrent.is_multifile
        self.active_peers = []
        self.output_dir: str = output_dir or DOWNLOAD_DIR

        if b"info" not in self.torrent.torrent_data:
            raise ValueError("Torrent data does not contain 'info' key")
        name = self.torrent.torrent_data[b"info"][b"name"].decode('utf-8')
        self.output_name: str = os.path.join(output_dir, name)
        self.output_name = get_unique_filename(self.output_name)
        self.num_pieces = torrent.number_of_pieces
        logger.info(f"PieceManage::__init__ number of pieces need to download is {self.num_pieces}")

        if self.haveMultiFile:
            self.total_length = 0
            self.file_limit = []
            for path, len in torrent.files:
                self.total_length = self.total_length + len
                self.file_limit.append(path, len, self.total_length)
            os.makedirs(self.output_name, exist_ok=True)
            for relative_path, len in torrent.files:
                # relative_path = relative_path.decode("utf-8")
                filepath = os.path.join(self.output_name, relative_path)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as file:
                    file.truncate(len)
        else:
            len = self.torrent.torrent_data[b"info"][b"length"]
            with open(self.output_name, "wb") as f:
                f.truncate(len)

    def get_request_message(self) -> Optional[Request]:
        piece_length = self.torrent.piece_length
        len = self.total_length if self.haveMultiFile else self.torrent.torrent_data[b"info"][b"length"]

        for stat in (PieceStatus.MISSING, PieceStatus.PENDING):
            for index, status in enumerate(self.pieces_status):
                if status == stat:
                    self.pieces_status[index] = PieceStatus.PENDING
                    request_length = len % piece_length if (index == self.torrent.number_of_pieces - 1) else piece_length 
                    return Request(index, 0, request_length).encode()
        return None


    # def _prepare_output(self):
    #     if self.haveMultiFile:
    #         os.makedirs(self.output_name, exist_ok=True)
    #         current_offset = 0
    #         for path, len in self.torrent.files:
    #             curr_path = os.path.join(*path)
    #             full_path = os.path.join(self.output_name, curr_path)
    #             os.makedirs(os.path.dirname(full_path), exist_ok=True)
    #             if not os.path.exists(full_path):
    #                 with open(full_path, 'wb') as f:
    #                     # Không cần cấp phát trước dung lượng cho đơn giản
    #                     # f.truncate(length)
    #                     pass
    #             current_offset += len
    #     else:
    #         os.makedirs(os.path.dirname(self.output_name), exist_ok=True)
    #         # Tạo file rỗng và cấp phát dung lượng trước (có thể giúp hiệu năng ghi)
    #         with open(self.output_name, 'wb') as f:
    #             try:
    #                 f.seek(self.torrent.total_size - 1)
    #                 f.write(b'\0')
    #             except OSError:
    #                 logging.warning(
    #                     f"Could not pre-allocate file space for {self.output_name}. Proceeding without pre-allocation.")
    #             except Exception as e:
    #                 logging.warning(f"Unexpected error during pre-allocation for {self.output_name}: {e}")

    async def _get_next_piece_index(self) -> Optional[int]:
        """Tìm và đánh dấu piece MISSING tiếp theo là PENDING."""
        async with self._lock:
            for index, status in enumerate(self.pieces_status):
                if status == PieceStatus.MISSING:
                    self.pieces_status[index] = PieceStatus.PENDING
                    logger.info(f"Marked piece {index} as PENDING.")
                    return index
            return None  # Không còn piece nào MISSING

    async def get_request_msg(self) -> Optional[bytes]:
        piece_index = await self._get_next_piece_index()
        if piece_index is None:
            logger.info("No missing piece to request")
            return None

        piece_size = self.torrent.piece_length
        if piece_index == self.torrent.number_of_pieces - 1: #truong hop la piece cuoi cung
            piece_size = self.torrent.total_size % piece_size

        begin_offset = 0
        request_msg = Request(piece_index, begin_offset, piece_size)
        logger.info(f"Created request for piece {piece_index}, offset {begin_offset}, length {piece_size}")
        return request_msg.encode()

    def validate_received_piece(self, data: bytes, index: int) -> bool:
        """Kiểm tra SHA1 hash của dữ liệu piece nhận được."""
        if not data:
            logger.warning(f"Validation failed for piece {index}: Received empty data.")
            return False
        # expected_hash = self.torrent.pieces_hash_concatenated[index * 20: (index + 1) * 20]
        expected_hash = self.torrent.torrent_data[b"info"][b"pieces"][(index * 20): ((index + 1) * 20)]
        calculated_hash = hashlib.sha1(data).digest()
        is_valid = calculated_hash == expected_hash
        if not is_valid:
            logger.warning(
                f"Hash mismatch for piece {index}! Expected: {expected_hash.hex()}, Got: {calculated_hash.hex()}")
            fullhash = self.torrent.torrent_data[b"info"][b"pieces"]
            logger.warning(f"Full hash is {fullhash.hex()}")
        return is_valid
    
    async def write_piece_to_file(self, index: int, data: bytes):
        logger.info(f"Writing piece {index} to file")
        piece_length = self.torrent.piece_length
        if self.haveMultiFile:
            lower_bound = index * piece_length
            upper_bound = lower_bound + len(data) - 1
            tmp = 0
            for path, len, limit in self.file_limit:
                if lower_bound + tmp >= limit: 
                    continue
                write_pos = lower_bound + tmp - limit + len
                if upper_bound < limit:
                    async with aiofiles.open(os.path.join(self.output_name, path), "rb+") as f:
                        await f.seek(write_pos)
                        await f.write(data[tmp:])
                        logger.info(f"Written {len(data)} bytes to {self.output_name}")
                    break
                else:
                    write_len = upper_bound - (lower_bound + tmp)
                    async with aiofiles.open(os.path.join(self.output_name, path), "rb+") as f:
                        await f.seek(write_pos)
                        await f.write(data[tmp:tmp+write_len])
                        logger.info(f"Written {len(data)} bytes to {self.output_name}")
                    tmp += write_len    
        else: #don file
            async with aiofiles.open(self.output_name, "rb+") as f:
                await f.seek(index * piece_length)
                await f.write(data)
                # self.pieces_status[index] = PieceStatus.COMPLETED
            # logger.info(f"Written {len(data)} bytes to {self.output_name}")

    async def receive_piece(self, data : bytes):
        """Xử lý dữ liệu piece nhận được từ peer."""
        # <message ID> = 1 byte(value = 7)
        # <index> = int = 4 byte
        # <begin> = int = 4 byte
        # <block> = data sent
        if len(data) < 9:
            raise Exception("PeerManage::receive_piece::Received piece data is too short.")
        # id, index, begin = struct.unpack(f'>bII', data[:9])
        id = data[0]
        index = struct.unpack('>I', data[1:5])[0]
        begin = struct.unpack('>I', data[5:9])[0]
        # logger.info(f"Received piece data: id={id}, index={index}, begin={begin}")
        if index < 0 or index >= self.torrent.number_of_pieces:
            raise Exception(f"PeerManage::receive_piece::Invalid piece index received: {index}")
        recv_data = data[9:]
        # logger.info(f"From received_piece: Received piece {index} with block length {len(recv_data)} bytes")
        if id != PeerMessage.Piece:
            raise Exception("Received an invalid piece data, id != PeerMessage.Piece")
        if not self.validate_received_piece(recv_data, index):
            raise Exception("Received an invalid piece data, validate_received_piece(recv_data, index)")
        if self.pieces_status[index] == PieceStatus.COMPLETED:
            logger.info(f"Received piece {index} which is already completed. Ignoring.")
            return None

        #ghi vao file
        try:
            await self.write_piece_to_file(index, recv_data)
            self.pieces_status[index] = PieceStatus.COMPLETED
            self.completed = all([x == PieceStatus.COMPLETED for x in self.pieces_status])
            for x in self.pieces_status:
                logger.info(f"Piece status: {x}")
            logger.info(f"Successfully received and saved piece {index}.")
            if self.completed:
                logger.info("All pieces have been downloaded!")
            return index #tra ve index bao hieu thanh cong
        except Exception as e:
            logger.error(f"receive_piece::Unexpected error with piece {index}: {str(e)}", exc_info=True)
            return None #ghi khong thanh cong



    







        