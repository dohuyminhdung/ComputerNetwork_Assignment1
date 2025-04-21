import hashlib
from peer_config import *
import time
from typing import List, Tuple, Union, Dict, Any, Optional
import bencodepy


def decode_keys(data):
    if isinstance(data, dict):
        return {(key.decode('utf-8') if isinstance(key, bytes) else key): decode_keys(value)
                for key, value in data.items()}
    elif isinstance(data, list):
        return [decode_keys(item) for item in data]
    else:
        return data

class TorrentFile:
    """"
    Arg     : đường dẫn file torrent
    Property:
        filename        : tên file/folder
        decoded_data    : dữ liệu đã được giải mã từ file torrent dưới dạng dictionary (json)
        info            : nhãn 'info' của file torrent dưới dạng json
        info_hash       : info_hash (SHA-1 của dictionary 'info' đã được bencode) dưới dạng bytes
        info_hash_hex   : info_hash dưới dạng chuỗi hexa
        announce        : URL tracker chính từ key 'announce'
        announce_list   : danh sách tracker từ key 'announce-list'
        piece_length    : kích thước mỗi piece (byte)
        pieces_hash_concatenated: chuỗi bytes nối liền của tất cả các mã hash SHA-1 của các piece
        number_of_pieces: số lượng piece trong torrent
        total_size      : tổng kích thước của tất cả các file trong torrent (bytes)
        is_multifile    : cho biết torrent chứa medata của file hay folder
        files           : danh sách các tuple cho torrent đa file.
                          mỗi tuple chứa danh sách đường dẫn và kích thước file
                          danh sách rỗng nếu là torrent đơn file.

    Methods:
        get_info_hash   : trả về info_hash (SHA-1) cho file torrent được truyền vào
        create_torrent_file: Tạo một file .torrent mới từ một file hoặc thư mục
    """
    def __init__(self, torrent_filepath: str):
        """
        Khởi tạo đối tượng TorrentFile bằng cách tải và phân tích dữ liệu từ một file .torrent hiện có.
        Args: torrent_filepath (str): Đường dẫn đến file .torrent.
        Attribute: _decoded_data (medata dc giai ma); _info_hash: info dc ma hoa SHA1
        """
        # logger.info(f"Đường dẫn tệp torrent trong __init__: {torrent_filepath}")
        if not os.path.isfile(torrent_filepath):
            raise FileNotFoundError(f"ERROR::peer_file::__init__::File {torrent_filepath} does not exists")
        self.torrent_filepath = torrent_filepath
        try:
            with open(torrent_filepath, 'rb') as f:
                self._decoded_data = bencodepy.decode(f.read())
            # self._decoded_data = self._decode_keys(decoded_data)
            if b"info" not in self._decoded_data:
                raise ValueError("Torrent data does not contain 'info' key")
            logger.debug(f"TorrentFile__init__::Decoded torrent data: {self._decoded_data}")
        except bencodepy.DecodingError as e:
            raise ValueError(f"Error decode file torrent '{torrent_filepath}': {e}") from e
        except Exception as e:
            raise ValueError(f"Error in TorrentFile __init__ with file '{torrent_filepath}': {e}") from e
        # Tính toán và lưu trữ info_hash
        try:
            info_bencoded = bencodepy.encode(self._decoded_data[b"info"])
            self._info_hash = hashlib.sha1(info_bencoded).digest()
        except Exception as e:
            raise ValueError(f"Can not calculate the info_hash: {e}") from e

    def _decode_keys(self, data):
        if isinstance(data, dict):
            decoded_dict = {}
            for key, value in data.items():
                if isinstance(key, bytes):
                    decoded_key = key.decode('utf-8')
                else:
                    decoded_key = key
                decoded_dict[decoded_key] = self._decode_keys(value)
            return decoded_dict
        elif isinstance(data, list):
            return [self._decode_keys(item) for item in data]
        else:
            return data
    def _decode_keys(self, data):
        if isinstance(data, dict):
            decoded_dict = {}
            for key, value in data.items():
                if isinstance(key, bytes):
                    decoded_key = key.decode('utf-8')
                else:
                    decoded_key = key
                # Giải mã giá trị nếu cần
                if isinstance(value, bytes):
                    try:
                        value = value.decode('utf-8')
                    except UnicodeDecodeError:
                        pass  # Giữ nguyên nếu không phải chuỗi UTF-8
                decoded_dict[decoded_key] = self._decode_keys(value)
            return decoded_dict
        elif isinstance(data, list):
            return [self._decode_keys(item) for item in data]
        else:
            return data


    @property 
    def filepath(self) -> str:
        return self.torrent_filepath
    
    @property
    def tracker_url(self) -> str:
        return TorrentFile.get_tracker_url(self.filepath)

    @property
    def torrent_data(self): #-> Dict[str, Any]:
        """Trả về dữ liệu đã được giải mã từ file torrent"""
        return self._decoded_data
        #self._decoded_data = bencodepy.decode(f.read())

    @property
    def info_hash(self) -> bytes:
        """Trả về info_hash (SHA-1 của dictionary 'info' đã được bencode) dưới dạng bytes."""
        return self._info_hash

    @property
    def info_hash_hex(self) -> str:
        """Trả về info_hash dưới dạng chuỗi hexa."""
        return self._info_hash.hex()

    @property
    def info(self) -> Dict[str, Any]:
        """Trả về dictionary 'info'."""
        return self._decoded_data.get(b"info", {})

    @property
    def piece_length(self) -> int:
        """Trả về kích thước của mỗi mảnh (piece) tính bằng byte."""
        return self.info[b"piece length"]

    @property
    def pieces_hash_concatenated(self) -> bytes:
        """Trả về chuỗi bytes nối liền của tất cả các mã hash SHA-1 của các mảnh."""
        return self.info.get('pieces', b'')

    @property
    def number_of_pieces(self) -> int:
        """Trả về tổng số lượng mảnh trong torrent."""
        # Mỗi hash SHA-1 dài 20 bytes
        return len(self.info[b"pieces"]) // 20

    @property
    def total_size(self) -> int:
        """Trả về tổng kích thước của tất cả các file trong torrent (bytes)."""
        if b'files' in self.info:
            # Torrent đa file
            return sum(file_info.get(b'length', 0) for file_info in self.info.get(b'files', []))
        else:
            # Torrent đơn file
            return self.info.get(b'length', 0)

    @property
    def is_multifile(self) -> bool:
        """Kiểm tra xem đây có phải là torrent đa file hay không."""
        return 'files' in self.info

    @property
    def files(self) -> List[Tuple[str, int]]: #str: path_to_file -> int: size_of_file
        """
        Trả về danh sách các tuple cho torrent đa file.
        Mỗi tuple chứa: (danh sách các thành phần đường dẫn tương đối dạng str, kích thước file dạng int).
        Trả về danh sách rỗng nếu là torrent đơn file.
        """
        if not self.is_multifile:
            return []
        
        info = self._decoded_data[b"info"]
        name = info[b"name"].decode()
        file_list = info[b"files"]
        files = [
            (file[b"path"],
             file[b"length"]) for file in file_list
        ]
        paths = [(os.path.join(*[part.decode('utf-8') for part in path_parts]),
                  length)
                    for path_parts, length in files
                 ]
        return paths
    
    @property
    def filename(self) -> str:
        if b"info" not in self._decoded_data or b"name" not in self._decoded_data[b"info"]:
            raise KeyError(f"Invalid torrent data: 'name' field is missing in 'info'")
        filename = self._decoded_data[b"info"][b"name"].decode("utf-8")
        return filename

# ======================================================================================================================
    @staticmethod
    def _generate_file_pieces(data_path, piece_length: int = 256 * 1024):
        """
            Generate concatenated SHA-1 hashes of all file pieces.
                Args:       data_path: Path to the file/dict
                Returns:    Concatenated SHA-1 hashes of all file(s) pieces (in binary format)
        """
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Invalid path: {data_path}")
        
        pieces = []
        if os.path.isdir(data_path): #case dict
            files = []
            total_data = b''
            for dict, sub_dict, files in os.walk(data_path):
                for file in files:
                    file_path = os.path.join(dict, file)
                    relative_path = os.path.relpath(file_path, start=data_path).split(os.sep) #path a\b\c => [a,b,c]
                    files.append({
                        "length": os.path.getsize(file_path), #size of single file of the dict
                        "path": relative_path                #a,b,c => for gernerate path a\b\c
                    })

                    with open(file_path, 'rb') as f:
                        while True:
                            piece = f.read(piece_length)
                            if not piece:
                                break
                            total_data += piece
                            if len(total_data) >= piece_length:
                                pieces.append(hashlib.sha1(total_data).digest())
                                total_data = total_data[piece_length:]
            if len(total_data) > 0: #final piece
                pieces.append(hashlib.sha1(total_data).digest())
            return b''.join(pieces), files
        else:   #case single file
            with open(data_path, 'rb') as f:
                while True:
                    piece = f.read(piece_length)
                    if not piece:
                        break
                    pieces.append(hashlib.sha1(piece).digest())
            return b''.join(pieces) # Concatenate all the SHA-1 hashes and return them as a single byte string


    @classmethod
    def _create_torrent_file(cls, 
                             input_path: str,
                             trackers: Union[str, List[str], List[List[str]]], 
                             output_path: str = None,
                             piece_size: int = PIECE_SIZE,
                             comment: str = '',
                             created_by: str = 'TorrentFile Class'):
        """
            Tạo một file .torrent mới từ một file hoặc thư mục.
                Args:
                    input_path: Đường dẫn đến file hoặc thư mục nguồn.
                    trackers: URL(s) tracker (Hỗ trợ nhiều định dạng)
                    output_path: Đường dẫn để lưu file .torrent mới.
                    piece_size: Kích thước mỗi mảnh (bytes).
                    comment: Note (Optional).
                    created_by: Tên ứng dụng hoặc người tạo torrent.
        """
        # logger.info(
        #     f"_create_torrent_file received: input_path='{input_path}' (type: {type(input_path)}), piece_size={piece_size} (type: {type(piece_size)})")
        announce = ""
        announce_list = []
        if isinstance(trackers, str): #truong hop la string
            announce = trackers
            announce_list = [trackers]
        elif isinstance(trackers, list):
            if isinstance(trackers[0], str):
                announce = trackers[0]
                announce_list = [tracker for tracker in trackers]
            else: 
                announce = trackers[0][0]
                for tracker_list in trackers:
                    for tracker in tracker_list:
                        announce_list.append(tracker)                                

        torrent = {
            "announce": announce,
            "announce-list": announce_list,
            "creation date": int(time.time()),
            "created by": created_by,
            "comment": comment,
            "info":{
                "piece length": piece_size,  # The length of each piece
                "name": os.path.basename(input_path),  # Name of the file/directory
            } 
        }            
        if os.path.isfile(input_path):
            torrent["info"]["length"] = os.path.getsize(input_path)
            torrent["info"]["pieces"] = cls._generate_file_pieces(input_path, piece_size)     
        else:
            pieces, file_list = cls._generate_file_pieces(input_path, piece_size)
            torrent["info"]["files"] = file_list
            torrent["info"]["pieces"] = pieces
        
        # Encode the torrent data using bencode
        # logger.info("Dữ liệu torrent trước khi mã hóa:", torrent)
        encoded_data = bencodepy.encode(torrent)
        
        dir_name = os.path.dirname(input_path)
        file_name = os.path.basename(input_path)

        output_path = output_path or f"{dir_name}/{file_name}.torrent"
        output_path = get_unique_filename(output_path)
        with open(output_path, 'wb') as f:
            f.write(encoded_data)
        # logger.info(
        #     f"Tệp .torrent đã được ghi tại: {output_path}, kích thước: {os.path.getsize(output_path)} bytes")
        return output_path

    @classmethod
    def get_info_hash(cls, torrent_filepath: str) -> bytes:
        """
            Đọc file .torrent, lay nhan 'info', bencode và tinh info_hash SHA-1.
            :param torrent_filepath: duong dan den file .torrent
            :return: info_hash duoi dang bytes
        """
        if not os.path.exists(torrent_filepath):
            raise FileNotFoundError(f"Invalid path: {torrent_filepath}")
        try:
            with open(torrent_filepath, 'rb') as f:
                decoded_data = bencodepy.decode(f.read())
            info_dict = decoded_data[b"info"]
            info_hash = hashlib.sha1(bencodepy.encode(info_dict)).digest()
            return info_hash
        except Exception as e:
            logger.error(f"get_info_hash::Error while processing file {torrent_filepath}: {e}")


    @classmethod
    def get_tracker_url(cls, torrent_filepath: str) -> str:
        try:
            with open(torrent_filepath, 'rb') as f:
                metadata = bencodepy.decode(f.read())
                # metadata = decode_keys(metadata)
                tracker_url = metadata[b"announce"].decode("utf-8")
                return tracker_url
        except FileNotFoundError:
            raise FileNotFoundError(f"The file '{torrent_filepath}' does not exist.")
        except bencodepy.DecodingError:
            raise ValueError("The file is not in a valid Bencoded format.")

##################################### DEBUG ###################################################
def main():
    f = TorrentFile(torrent_filepath="G:\Y3S2\MMT\BTL\Chapter_7_v8.0.pdf.torrent")
    fullhash = f.torrent_data[b"info"][b"pieces"]
    print(fullhash.hex())
    fullhash = f.info_hash_hex
    print(fullhash)
if __name__ == "__main__":
    main()







        
