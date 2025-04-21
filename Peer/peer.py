from typing import Dict, Any, List, Optional, Union, Tuple
import requests
from tqdm import tqdm
from uuid import uuid4
from peer_config import *
from peer_download import *

# seeding fomat
        # {
        #     <info_hash_1>: {
        #         "filepath": "<filepath>"
        #         "torrent_filepath": "<torrent_filepath>"
        #     },
        #     <info_hash_2>: {
        #         "filepath": "<filepath>"
        #         "torrent_filepath": "<torrent_filepath>"
        #     }
        # }

class Peer:
    def __init__(self, peer_port : int = None):
        self.port = peer_port or 6881
        self.ip = get_local_ip()
        # Sử dụng info_hash làm key
        """
        self.seeding_torrents[torrent.info_hash] = {
                "torrent_filepath": torrent.filepath,
                "filepath": input_path
            }
        """
        self.seeding_torrents = {}
        self.leeching_torrents = {}
        self.peer_id = os.urandom(50)
        # logger.info(f"Peer initialized with ID: {self.peer_id.hex()}, listening on {self.ip}:{self.port}")


    def _get_tracker_urls(self, torrent: TorrentFile) -> List[str]:
        """Lấy danh sách URL tracker hợp lệ từ file torrent."""
        urls = []
        if torrent.announce_list:
            for tier in torrent.announce_list:
                urls.extend(tier)
        if torrent.announce and torrent.announce not in urls:
            urls.insert(0, torrent.announce)  # Ưu tiên announce chính
        # Lọc bỏ các URL không hợp lệ hoặc trùng lặp (ví dụ None)
        return [url for url in urls if isinstance(url, str) and url.startswith(('http://', 'https://'))]

    def _send_request_to_tracker(self, torrent_filepath: str, event: str = None) -> requests.Response:
        torrent = TorrentFile(torrent_filepath)
        tracker_url = torrent.get_tracker_url(torrent_filepath=torrent_filepath)
        logger.info(f"At _send_request_to_tracker, Tracker URL is: {tracker_url}")
        dict = {
            "info_hash": torrent.info_hash.hex(),
            "peer_id": self.peer_id,
            "port": self.port,
            "ip": self.ip
        }

        if event:
            dict["event"] = event
        try:
            response = requests.get(tracker_url + "/announce", params=dict, timeout=20)
            response.raise_for_status()  # Raise error if status is not 200
            return response
        except requests.exceptions.Timeout:
                logger.warning(f"Timeout connecting to tracker: {tracker_url}")
        except requests.exceptions.RequestException as e:
                logger.warning(f"Error connecting to tracker.\nError: {str(e)}")
        except Exception as e:
            logger.error(f"Error occurs in _send_request_to_tracker: {str(e)}")
            raise

    def _upload_torrent_to_tracker(self, name : str, description: str, torrent_filepath: str) -> Optional[requests.Response]:
        torrent = TorrentFile(torrent_filepath)
        tracker_url = torrent.get_tracker_url(torrent_filepath)
        logger.info(f"At _upload_torrent_to_tracker, Tracker URL is: {tracker_url}")
        with open(torrent_filepath, "rb") as f:
            files = {"file": f}
            params = {
                "info_hash": torrent.info_hash.hex(),
                "peer_id": self.peer_id,
                "port": self.port,
                "ip": self.ip,
                "event": "started"
            }
            data = {
                    "name": name,
                    "description": description
                }
            try:
                response = requests.post(tracker_url + "/announce", files=files, data=data, params=params, timeout=20)
                response.raise_for_status()
                logger.info(f"Successfully uploaded torrent '{name}'")
                return response
            except requests.exceptions.Timeout:
                    logger.warning(f"Timeout uploading to tracker: {tracker_url}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error uploading to tracker {tracker_url}: {e}")
            except Exception as e:
                    logger.error(f"Error occurs in _upload_torrent_to_tracker: {(e)}")
                    raise

    def _sow_seed(self, input_path: str,
                        trackers: Union[str, List[str], List[List[str]]],
                        public: bool = True,
                        piece_length: int = PIECE_SIZE,
                        torrent_filepath: str = None,
                        **kwargs):
        """
        Tạo file torrent từ dữ liệu và bắt đầu seed.
        Args:
            input_path: Đường dẫn đến file hoặc thư mục cần seed.
            trackers: URL tracker hoặc danh sách tracker.
            public: True để upload torrent lên tracker, False chỉ thông báo "started".
            piece_length: Kích thước mỗi piece (bytes).
            torrent_filepath: Đường dẫn lưu file .torrent (tự động nếu None).
            kwargs: Các tham số bổ sung (name, description) cho upload.
        """
        # logger.info(
        #     f"_sow_seed received: input_path='{input_path}' (type: {type(input_path)}), piece_length={piece_length} (type: {type(piece_length)})")
        if not os.path.exists(input_path):
            raise FileNotFoundError(input_path, "does not exists.")
        try:
            #setup
            torrent_filepath = TorrentFile._create_torrent_file(
                input_path=input_path,
                trackers=trackers,
                output_path=torrent_filepath or os.path.join(DOWNLOAD_DIR, os.path.basename(input_path)+".torrent"),
                piece_size=piece_length
            )
            logger.info(f"Đường dẫn tệp torrent được tạo: {torrent_filepath}")
            # with open(torrent_filepath, 'rb') as f:
            #     decoded_data = bencodepy.decode(f.read())
            #     logger.info(("Dữ liệu giải mã từ tệp .torrent:", decoded_data))
            torrent = TorrentFile(torrent_filepath)

            self.seeding_torrents[torrent.info_hash] = {
                "torrent_filepath": torrent.filepath,
                "filepath": input_path
            }
            #upload
            if public:
                name = kwargs.get("name", None) or torrent.filename
                description = kwargs.get("description", "")
                self._upload_torrent_to_tracker(name, description, torrent.filepath)
            else:
                self._send_request_to_tracker(torrent.filepath, "started")
        except FileNotFoundError as e:
            logger.error(f"FileNotFoundError occurs in _sow_seed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error occurs during sow_seed for '{input_path}': {e}", exc_info=True)
            raise

    def _seed_after_downloading(self, input_path: str, input_torrent_filepath: str):
        self._send_request_to_tracker(input_torrent_filepath, event="started")
        try:
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"'{input_path}' does not exists.")
            if not os.path.exists(input_torrent_filepath):
                raise FileNotFoundError(f"{input_torrent_filepath} does not exists.")

            torrent = TorrentFile(input_torrent_filepath)
            # Kiểm tra xem torrent đã có trong danh sách seeding chưa
            if torrent.info_hash in self.seeding_torrents:
                logger.warning(f"Torrent '{torrent.filename}' (Hash: {torrent.info_hash}) is already in seeding list.")
                # Có thể chỉ cần gửi lại announce nếu cần
                # self.send_request_to_tracker(input_torrent_filepath, event="started", left=0)
                return

            self.seeding_torrents[torrent.info_hash] = {
                "torrent_filepath": torrent.filepath,
                "filepath": input_path
            }
            self._send_request_to_tracker(input_torrent_filepath, event="started")
            logger.info(f"Added completed torrent '{torrent.filename}' (Hash: {torrent.info_hash}) to seeding list.")
        except FileNotFoundError as e:
            logger.error(f"File not found during seed_after_downloading: {str(e)}")
        except Exception as e:
            logger.error(f"Error during _seed_after_downloading for '{input_path}': {str(e)}", exc_info=True)


    async def _get_piece_for_seeding(self,
                                    torrent: TorrentFile,
                                    torrent_info: Dict,
                                    index: int,
                                    length: int): # -> Optional[bytes]:
        """
        Lấy dữ liệu block(piece) (index, length) từ file/folder đang seed.
        Args:
            torrent: torrent file đang seed
            torrent_info: Dict chứa thông tin torrent đang seed từ self.seeding_torrents.
            index: Chỉ số piece.
            length: Độ dài block cần đọc (bytes).
        Returns:
            Dữ liệu block (bytes) hoặc None nếu có lỗi.
        """
        piece_length = torrent.piece_length
        data_path = torrent_info["filepath"]
        # logger.info(f"_get_piece_for_seeding::Piece {index} from {data_path}")
        try:
            if not torrent.is_multifile: #Trường hợp Single File
                async with aiofiles.open(data_path, "rb") as f:
                    # await f.seek(index * piece_length)
                    await f.seek(index * piece_length)
                    block_data = await f.read(length)
                    # Debug: Lưu dữ liệu piece gửi đi
                    # with open(f"piece_{index}_sent.bin", "wb") as f:
                    #     f.write(block_data)
            else: #Trường hợp Multi-file
                block_data = b""
                offset = index * piece_length
                read_len = length
                for path, file_size in torrent.files:
                    if offset < file_size:
                        async with aiofiles.open(os.path.join(data_path, path), "rb") as f:
                            await f.seek(offset)
                            block_data += await f.read(read_len)
                        if len(block_data) == length:
                            break
                        read_len = length - len(block_data)
                        offset = 0
                    else:
                        offset = offset - file_size
            hash_before = hashlib.sha1(block_data).digest()
            # logger.info(f"_get_piece_for_seeding::Hash before sent to client is {hash_before.hex()}, from {data_path}")
            return block_data
        except IOError as e:
            logger.error(f"IOError getting piece index {index}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting piece index {index}: {e}", exc_info=True)
            return None


    async def _handle_uploader(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
                Xử lý kết nối từ một leecher (client yêu cầu dữ liệu) để seed file.
                Thực hiện handshake, gửi dữ liệu piece theo yêu cầu, và quản lý KeepAlive.
        """
        addr = writer.get_extra_info("peername")
        try:
            #xac thuc handshake
            request = await asyncio.wait_for(reader.read(68), timeout=10) #read 68 byte handshake
            if not request:
                raise Exception(f"Connection to client {addr} closed")
            if not Handshake.is_valid(request):
                raise Exception("Seeder: Handshake response is not valid")

            #decode handshake nhan duoc de lay info hash
            handshake_request = Handshake.decode(request)
            info_hash = handshake_request.info_hash
            #xac dinh torrent can seed
            if info_hash not in self.seeding_torrents:
                raise Exception(f"Seeder: No seed torrent with info_hash {info_hash} in this peer. Connection closed.")

            torrent_info = self.seeding_torrents[info_hash]
            torrent = TorrentFile(torrent_info["torrent_filepath"])

            #gui handshake phan hoi #gui ack
            response_handshake = Handshake(info_hash).encode() #gui lai in4 hash nhan dc

            writer.write(response_handshake)
            await writer.drain()
            # logger.info(f"peer::_handle_uploader::Seeder: reply handshake has been sent.")

            #Lang nghe va xu ly yeu cau
            max_attempts = 300
            total_hash = len(self.seeding_torrents)
            attempts = 0
            while attempts < max_attempts:
                # Đọc độ dài message (4 bytes) với timeout
                message = await asyncio.wait_for(reader.read(4), timeout=12)
                if not message:
                    break
                #message = 13 or -1 if Done
                # PeerMessage.Request, 1b
                # self.index,   4b
                # self.begin,   4b
                # self.length   4b
                message_length = struct.unpack('>I', message)[0] #13
                if message_length == -1:
                    break
                message = await asyncio.wait_for(reader.read(message_length), timeout=12)
                (id, index, begin, length) = struct.unpack('>bIII', message)
                piece = await self._get_piece_for_seeding(torrent, torrent_info, index, length)
                piece_message = Piece(index, begin, piece).encode()
                writer.write(piece_message)
                await writer.drain()
                tqdm.write(f"Sent PIECE with index {index} to peer {addr}")
                attempts += 1
            writer.close()
            await writer.wait_closed()
        except asyncio.CancelledError:
            logger.info(f"Seeder: Peer had closed connection (IncompleteReadError).")
            raise
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError) as e:
            logger.info(f"Seeder: Connection closed by peer during operation. Reason: {type(e).__name__}")
            raise
        except Exception as e:
            logger.error(f"Seeder: Unexpected error handling connection: {e}", exc_info=True)
            raise
        finally:
            logger.info(f"Closed connection to {addr}")



    def _get_peers(self, torrent_filepath: str) -> Dict[str, Any]: #Dict[str, Any]:
        try:
            response = self._send_request_to_tracker(torrent_filepath)
            data = response.json()
            peers = data.get("peers", {})
            if not peers:
                logger.warning("Tracker returned no peers.")
            else:
                logger.info(f"Received {len(peers)} peers from tracker.")
            return peers
        except Exception as e:
            logger.error(f"Error getting peers from tracker: {e}")
            return {}

    @staticmethod
    def get_torrents():
        try:
            response = requests.get(TRACKER_URL + "/torrents")
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            torrents = response.json()
            return torrents
        except requests.HTTPError as e: # HTTP errors (404, 500, ...)
            raise RuntimeError(f"HTTP error occurred: {e}") from e
        except requests.RequestException as e: # Other requests issues
            raise RuntimeError(f"Request error occurred: {e}") from e
        except Exception as e:
            raise Exception("Error occured during getting torrents from tracker") from e

    async def _get_torrent_by_info_hash(info_hash: bytes):
        try:
            response = requests.get(TRACKER_URL + f"/torrents/{info_hash}")
            response.raise_for_status()

            torrent_filepath = os.path.join(DOWNLOAD_DIR, str(uuid4()))
            async with aiofiles.open(torrent_filepath, "wb") as f:
                await f.write(response.content)

            file_name = TorrentFile(torrent_filepath).filename
            logger.info(f"Type of filename: {type(file_name)}, Value: {file_name}")
            file_name = file_name + ".torrent"

            dir = os.path.dirname(torrent_filepath)
            new_torrent_filepath = get_unique_filename(os.path.join(dir, file_name))
            os.rename(torrent_filepath, new_torrent_filepath)
            return new_torrent_filepath
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTP error occurred: {e}") from  e
        except requests.RequestException as e:
            raise RuntimeError(f"Request error occurred: {e}") from e
        except Exception as e:
            raise Exception(f"Error occured during getting torrent by info_hash from tracker. {e}") from e

    async def _download_from_peer(self,
                                 piece_manager: PieceManage,
                                 torrent: TorrentFile,
                                 peer: Optional[Dict]):
        """
        Kết nối, handshake và tải các piece từ một peer.
        dict = {
            "info_hash": torrent.info_hash.hex(),
            "peer_id": self.peer_id,
            "port": self.port,
            "ip": self.ip
        }
        """
        peer_ip = peer.get("ip")
        peer_port = peer.get("port")
        try:
            # logger.info(f"Connecting to peer {peer_ip}:{peer_port}...")
            reader, writer = await asyncio.wait_for(asyncio.open_connection(peer_ip, peer_port), timeout=12)
            logger.info(f"Connected to {peer_ip}:{peer_port}")
            piece_manager.active_peers.append(peer)

            # --- Handshake ---
            handshake_msg = Handshake(info_hash=torrent.info_hash)
            writer.write(handshake_msg.encode())
            await writer.drain()
            logger.debug(f"Sent Handshake to {peer_ip}:{peer_port}")

            # Nhận handshake response
            try:
                response = await asyncio.wait_for(reader.read(Handshake.length), timeout=12)
                # Validate handshake
                if not Handshake.is_valid(response):
                    logger.warning(f"Received invalid handshake from {peer_ip}:{peer_port}")
                    return
            except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.TimeoutError) as e:
                logger.warning(f"No/Invalid handshake response from {peer_ip}:{peer_port}. Error: {e}")
                return  # Đóng kết nối

            _, _, _, recv_info_hash, _ = struct.unpack('>B19s8s20s20s', response)
                                                        # B = 1 byte = 19
                                                        # 19s = 19 byte string
                                                        # 8s = pad string
                                                        # 20s = info_hash
                                                        # 20s = pad string
            if recv_info_hash != torrent.info_hash:
                logger.warning(f"Peer::_download_from_peer::Info hash mismatch from {peer_ip}:{peer_port}.")
                logger.warning(f"Received invalid info_hash:: {recv_info_hash}")
                return
            logger.info(f"Handshake successful with {peer_ip}:{peer_port}")

            peer_is_unchoke = True  # Giả định peer đc unchoke từ đầu
            while peer_is_unchoke and not piece_manager.completed:
                try:
                    #gui yeu cau tai
                    request = piece_manager.get_request_message()
                    if not request:
                        logger.info(f"Take all pieces to needed from {peer}.")
                        break
                    writer.write(request)
                    await writer.drain()
                    #nhan phan hoi
                    length_prefix = await asyncio.wait_for(reader.readexactly(4), timeout=10 * 2)  # Chờ lâu hơn để bên kia ghi
                    if not length_prefix:
                        raise Exception(f"Connection to {peer} closed (NULL response after sending request).")
                    message_length = struct.unpack('>I', length_prefix[:4])[0] # >= 9
                    # logger.info(f"length_prefix = {length_prefix}. Received message_length = {message_length} bytes")

                    # <length prefix> = 9
                    # <message ID> = 1 byte(value = 7)
                    # <index> = int = 4 byte
                    # <begin> = int = 4 byte
                    # <block> = data sent
                    message_body = await asyncio.wait_for(reader.readexactly(message_length), timeout=24)
                    # <message ID> <index> <begin> <block>
                    # logger.info(f"Received message_body with length {len(message_body)} bytes")
                    if not message_body:
                        raise Exception(f"Connection to {peer} closed (response with NULL message body).")
                    if len(message_body) != message_length:
                        raise Exception(f"Incomplete message: expected {message_length}, got {len(message_body)}")
                    index = await piece_manager.receive_piece(message_body)
                    if index:
                        logger.info(f"Received piece with index {index} from {peer}.")
                except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError, asyncio.TimeoutError) as e:
                    logger.error(f"Connection error or timeout while waiting for Unchoke from {peer_ip}:{peer_port}: {e}")
                    raise
            # writer.write(struct.pack('>I', -1)) #Thank you, we can close connection now
            # await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            logger.error(f"Peer::_download_from_peer()::An error occurred when downloading piece(s): {str(e)}", exc_info=True)
        finally:
            if piece_manager and (peer in piece_manager.active_peers):
                piece_manager.active_peers.remove(peer)
            logger.info(f"Disconnected from peer {peer_ip}:{peer_port}")

    async def _download(self, torrent_filepath: str, output_dir: str = None, pbar_position: int = 0):
        """ Quản lý quá trình download """
        output_dir = output_dir or DOWNLOAD_DIR
        if not isinstance(output_dir, str):
            raise ValueError(f"output_dir phải là một chuỗi, nhận được {type(output_dir)}: {output_dir}")
        logger.info(f"--- Starting download: {torrent_filepath} ---")
        logger.info(f"Output directory: {output_dir}")

        torrent = TorrentFile(torrent_filepath)
        piece_manager = PieceManage(torrent=torrent, output_dir=output_dir)
        total_pieces = torrent.number_of_pieces

        max_attempts = 3  # Số lần thử tối đa khi không có peers
        attempt = 0
        try:
            with tqdm(total=total_pieces,
                      desc=f"DL {os.path.basename(torrent.filename)}",
                      position=pbar_position,
                      leave=True,
                      unit="piece") as pbar:

                while not piece_manager.completed and attempt < max_attempts:
                    peer_list = self._get_peers(torrent_filepath)

                    if not peer_list:
                        logger.warning("No peers available, retrying...")
                        attempt += 1
                        await asyncio.sleep(INTERVAL)
                        continue
                    attempt = 0  # Reset số lần thử nếu có peers

                    for p in peer_list:
                        if p not in piece_manager.active_peers :
                                asyncio.create_task(self._download_from_peer(piece_manager,torrent,p,pbar_position))
                    await asyncio.sleep(INTERVAL) #can sleep moi lan kiem tra
                if attempt >= max_attempts:
                    logger.error("Failed to download: No peers available after multiple attempts.")
                    return
            # --- Download Hoàn Thành ---
            logger.info("=" * 20)
            logger.info(f"Download {torrent.filename} success!!!")
            logger.info(f"File saved at: {piece_manager.output_name}")
            logger.info("=" * 20)
            # --- Chuyển sang seeding ---
            logger.info("Transitioning to seeding...")
            self._seed_after_downloading(input_path=piece_manager.output_name,
                                         input_torrent_filepath=piece_manager.torrent.filepath)
            logger.info(f"Now seeding: {piece_manager.output_name}")
        except Exception as e:
            logger.error(f"Unexpected error in download: {e}", exc_info=True)


    async def start_seeding(self):
        """
        Coroutine chính để khởi động server lắng nghe kết nối từ các peer khác.
        """
        try:
            # Khởi tạo server lắng nghe trên tất cả các địa chỉ IP có sẵn (0.0.0.0) và port đã chọn
            server = await asyncio.start_server(
                self._handle_uploader,  # Phương thức xử lý mỗi kết nối client mới
                host='0.0.0.0',  # Lắng nghe trên tất cả các interface mạng
                port=self.port or 6969  # Port được gán cho peer này
            )
            addr = server.sockets[0].getsockname()
            # logger.info(f"Peer start listening connection on {addr[0]}:{addr[1]}")
            # print(f"Peer start listening connection on {addr[0]}:{addr[1]}")

            async with server:
                await server.serve_forever()

        except KeyboardInterrupt:
            # Xử lý khi người dùng nhấn Ctrl+C
            # Sử dụng tqdm.write nếu bạn đang dùng progress bar, nếu không dùng logger hoặc print
            tqdm.write("Stopped with Keyboard Interrupt Ctrl+C")
            logger.info("Đã dừng chương trình bằng Ctrl+C")
        except Exception as e:
            # Bắt các lỗi không mong muốn khác
            tqdm.write(f"Error running peer server: {e}")
            logger.exception(f"Error running peer server: {e}")  # Ghi cả traceback
        finally:
            for stat in self.seeding_torrents.values:
                self._send_request_to_tracker( torrent_filepath=stat.get("torrent_filepath", ""), 
                                                event="stopped")
##################################### DEBUG ###################################################
def main():
    peer = Peer(peer_port=6881)
    peer._sow_seed(input_path="G:\Y3S2\MMT\Slide\Chapter_6_v8.0.pdf",
                   trackers=["http://127.0.0.1:8000"],
                   public=False)
    peers = peer._get_peers("G:\Y3S2\MMT\BTL\Chapter_6_v8.0.pdf.torrent")
    print(peers)
if __name__ == '__main__':
    main()