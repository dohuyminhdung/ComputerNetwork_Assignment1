import json
import logging
import os
import uuid
import click
import uvicorn

from werkzeug.utils import secure_filename
from typing import Dict, List, Any
from fastapi import FastAPI, Request, File, UploadFile, Form, Query, HTTPException, status
from fastapi.responses import RedirectResponse, FileResponse
# from Peer.config import

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = "G:\Y3S2\MMT\BTL\BTL1\p2pFileSharingApp"
TORRENT_DIR = os.path.join(BASE_DIR, "tracker_torrents") # Thư mục lưu file .torrent
PEER_FILE = os.path.join(BASE_DIR, "tracker_peers.json") # File lưu danh sách peers theo info_hash
TORRENT_FILE = os.path.join(BASE_DIR, "tracker_torrents.json") # File lưu metadata torrent
ANNOUNCE_INTERVAL = 1800 # Giây (30 phút)

os.makedirs(TORRENT_DIR, exist_ok=True)

# --- Cấu hình logging ---
log_file_path = os.path.join(LOG_DIR, 'tracker.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8')
    ]
)
logger = logging.getLogger("TorrentTracker")
# --- Kết thúc cấu hình logging ---

# Khởi tạo file JSON nếu chưa có
if not os.path.exists(TORRENT_FILE):
    with open(TORRENT_FILE, "w") as f:
        json.dump({}, f)
    logger.info(f"Initialized empty torrent metadata file: {TORRENT_FILE}")

if not os.path.exists(PEER_FILE):
    with open(PEER_FILE, "w") as f:
        json.dump({}, f)
    logger.info(f"Initialized empty peer file: {PEER_FILE}")

app = FastAPI()
peers = {}  # Dictionary lưu danh sách peers, ví dụ: {info_hash: [{"ip": ip, "port": port}, ...]}
# Exception response
class BadRequestError(HTTPException):
    def __init__(self, detail: str = "Bad Request Error."):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

def get_peers(peers, info_hash: str):
    peer_info_dict = peers.get(info_hash, [])
    if not peer_info_dict:
        logger.error(f"get_peers in tracker return 0 peer")
    peer_list: list[Dict[str, Any]] = []
    for peer in peer_info_dict:
        peer_list.append({
            "ip": peer["ip"],
            "port": peer["port"],
        })
    return peer_list

@app.get("/")
def get_status():
    return {"status": "Tracker is running."}

@app.get("/announce")
async def announce_get(request: Request,
                       info_hash: str = Query(...),
                       port: int = Query(...),
                       ip: str = Query(None),
                       event: str = Query(None),):
    public_ip = request.client.host
    peer = {"ip": ip or public_ip, "port": port}
    with open(PEER_FILE, "r") as f:
        peer_dict = json.load(f)

    if info_hash not in peer_dict:
        peer_dict[info_hash] = []
    # def add_peer(peer: Dict[str, Any]):
    #     if event == "started":
    #         if peer not in peer_dict[info_hash]:
    #             peer_dict[info_hash].append(peer)
    #             logger.info(f"Added peer {ip}:{port} for info_hash {info_hash}")
    #     elif event == "stopped":
    #         if peer in peer_dict[info_hash]:
    #             peer_dict[info_hash].remove(peer)
    # if ip != public_ip:
    #     add_peer({"ip": ip, "port": port})
    # add_peer({"ip": public_ip, "port": port})
    if event == "started":
        if peer not in peer_dict[info_hash]:  # Tránh trùng lặp
            peer_dict[info_hash].append(peer)
            logger.info(f"Added peer {peer['ip']}:{peer['port']} for info_hash {info_hash}")
    elif event == "stopped":
        if peer in peer_dict[info_hash]:
            peer_dict[info_hash].remove(peer)
            logger.info(f"Removed peer {peer['ip']}:{peer['port']} for info_hash {info_hash}")

    peer_list = get_peers(peer_dict, info_hash)
    try:
        with open(PEER_FILE, "w") as f:
            json.dump(peer_dict, f, indent=4)
    except Exception as e:
        logger.error(f"Error writing to PEER_FILE: {str(e)}")
        raise HTTPException(status_code=500, detail="Error saving peer data")
    reply = {"peers": peer_list, "interval": ANNOUNCE_INTERVAL}
    logger.info(f"Response for info_hash {info_hash}: {reply}")
    return reply



def decode_keys(data):
    """
    Giải mã các key (nếu là bytes) trong data (dict hoặc list) thành str.
    """
    if isinstance(data, dict):
        return {(key.decode('utf-8') if isinstance(key, bytes) else key): decode_keys(value)
                for key, value in data.items()}
    elif isinstance(data, list):
        return [decode_keys(item) for item in data]
    else:
        return data
@app.post("/announce")
async def announce_post(port: int = Query(...),
                        ip: str = Query(None),
                        info_hash: str = Query(...),
                        file: UploadFile = File(...),
                        name: str = Form(None),
                        comment: str = Form(None)):
    if not file.filename.endswith(".torrent"):
        raise BadRequestError("The processing file is not a .torrent file.")
    logger.info(f"Received announce for info_hash: {info_hash}")
    with open(TORRENT_FILE, "r") as f:
        torrent_dict = json.load(f)
        # torrent_dict = decode_keys(torrent_dict)
    logger.info(f"Current torrent_dict: {torrent_dict}")
    if info_hash not in torrent_dict or not os.path.exists(torrent_dict[info_hash]["file_path"]):
        file_path = os.path.join(TORRENT_DIR, f"{uuid.uuid4()}.torrent")
        with open(file_path, "wb") as f:
            f.write(await file.read())
        name = name + ".torrent" if name else file.filename
        if info_hash not in torrent_dict:
            torrent_dict[info_hash] = {}
            logger.info(f"Initialized new entry for {info_hash} from tracker announce_post")
        torrent_dict[info_hash]["file_path"] = file_path
        torrent_dict[info_hash]["name"] = name
        torrent_dict[info_hash]["description"] = comment
        with open(TORRENT_FILE, "w") as f:
            json.dump(torrent_dict, f, indent=4)
        logger.info(f"Updated torrent_dict: {torrent_dict}")
    return RedirectResponse(
        url=f"/announce?info_hash={info_hash}&port={port}&{'ip=' + ip + '&' if ip else ''}event=started",
        # url=f"/announce/{info_hash}&event=started",
        status_code=302
    )

@app.get("/torrents")
async def get_torrents():
    with open(TORRENT_FILE, "r") as f:
        torrent_dict = json.load(f)
    #loại bỏ thông tin "file_path" để ẩn thông tin nội bộ
    for info_hash in torrent_dict:
        if "file_path" in torrent_dict[info_hash]:
            del torrent_dict[info_hash]["file_path"]
    return torrent_dict

@app.get("/torrents/{info_hash}")
async def get_torrent(info_hash: str):
    with open(TORRENT_FILE, "r") as f:
        torrent_dict = json.load(f)
        if info_hash not in torrent_dict:
            raise BadRequestError("Info hash does not exist.")
    return FileResponse(path = torrent_dict[info_hash]["file_path"],
                        filename = torrent_dict[info_hash]["name"],
                        media_type = "application/octet-stream")
@click.command()
@click.option("--h", "host", default="127.0.0.1",  help="Running host for tracker")
@click.option("--p", "port", default=8000, help="Running port for tracker")
def main(host="127.0.0.1", port = 8000):
    uvicorn.run(app=app,
                host=host,
                port=port,
                reload=False)
if __name__ == "__main__":
    main()
























