import socket
import os
import logging

TRACKER_URL = "http://127.0.0.1:8000"
PIECE_SIZE: int = 256 * 1024
DOWNLOAD_DIR = "G:\Y3S2\MMT\BTL"
LOG_DIR = "G:\Y3S2\MMT\BTL\BTL1\p2pFileSharingApp"
INTERVAL = 12

os.makedirs(LOG_DIR, exist_ok=True)
log_file_path = os.path.join(LOG_DIR, 'peer_api.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8')
    ]
)

logger = logging.getLogger("PeerAPI-Quart")

def get_local_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    return local_ip

def get_unique_filename(file_path):
    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    while os.path.exists(os.path.join(directory, unique_filename)):
        unique_filename = f"{base}({counter}){ext}"
        counter += 1
    return os.path.join(directory, unique_filename)

############################################## DEBUG #####################################
import bencodepy
def main():
    with open(r'G:\Y3S2\MMT\BTL\Chapter_7_v8.0.pdf.torrent', 'rb') as f:
        data = bencodepy.decode(f.read())
    print(data)

if __name__ == "__main__":
    main()






















